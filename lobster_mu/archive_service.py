# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 压缩包上传后自动解压与文本提取。

设计目标：用户上传 .zip/.tar/.tgz/.gz 后，后台自动解压到该用户隔离目录，
逐文件提取文本，融入现有 {filename, content, stored_name} 下游契约（chat files / file_store）。
仅用标准库 zipfile/tarfile，不引入额外依赖（保证 Linux 部署稳定）。
.rar/.7z 不在本模块范围（维持"请下载解压"提示）。
"""
import os
import shutil
import zipfile
import tarfile

from lobster_mu.paths import uploads_dir, gen_filename
from lobster_mu.upload_service import extract_text

# 识别为可自动解压的扩展名
ARCHIVE_EXT = {".zip", ".tar", ".tgz", ".gz", ".tar.gz"}

# 安全限制
MAX_FILES = 200          # 单压缩包最多解压文件数
MAX_FILE_SIZE = 10 * 1024 * 1024   # 单文件 10MB
MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 总解压体积 50MB

# 噪声文件（macOS / Windows 元数据）
_NOISE_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
_NOISE_DIRS = {"__macosx", ".git", ".svn"}


def _is_noise(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    for p in parts[:-1]:
        if p.lower() in _NOISE_DIRS:
            return True
    return parts[-1].lower() in _NOISE_NAMES


def _safe_zip_names(zf: zipfile.ZipFile):
    """校验 zip 成员名防路径穿越，返回干净相对名列表（跳过目录/噪声/非法名）。"""
    names = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        raw = info.filename
        # 规范化为 / 分隔
        norm = raw.replace("\\", "/")
        parts = norm.split("/")
        if any(p == ".." for p in parts):
            continue
        if os.path.isabs(raw) or raw.startswith(("/", "\\")):
            continue
        # 取 basename 作为落盘名（丢弃子目录层级，避免复杂目录重建）
        base = os.path.basename(norm.rstrip("/"))
        if not base or _is_noise(norm):
            continue
        names.append(base)
    return names


def _safe_tar_names(tf: tarfile.TarFile):
    """校验 tar 成员防路径穿越/符号链接，返回干净 basename 列表。"""
    names = []
    for m in tf.getmembers():
        if not m.isfile():
            continue
        norm = m.name.replace("\\", "/")
        parts = norm.split("/")
        if any(p == ".." for p in parts):
            continue
        if os.path.isabs(m.name) or m.name.startswith(("/", "\\")):
            continue
        base = os.path.basename(norm.rstrip("/"))
        if not base or _is_noise(norm):
            continue
        names.append(base)
    return names


def process_archive_from_path(user_id: int, filename: str, content: bytes,
                              archive_path: str, archive_name: str = None) -> dict:
    """解压已落盘的压缩包（save_upload 先落盘再调本函数）。

    返回:
      成功: {"success": True, "stored_name": <压缩包存储名>,
             "files": [{filename, content, stored_name, size}],
             "skipped": [文件名...]}
      失败: {"success": False, "error": ...}
    """
    dest_root = uploads_dir(user_id)
    archive_name = archive_name or os.path.basename(archive_path)
    ext = os.path.splitext(filename or "")[1].lower()

    # 解压到临时子目录
    tmp_dir = os.path.join(dest_root, f".extract_tmp_{archive_name}")
    os.makedirs(tmp_dir, exist_ok=True)

    extracted = []  # (orig_name, abs_path)
    try:
        lower = (filename or "").lower()
        if ext == ".zip" or lower.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                safe_names = _safe_zip_names(zf)
                for base in safe_names:
                    # 在 zip 中查找对应成员（取第一个匹配 basename 的）
                    target = None
                    for info in zf.infolist():
                        if not info.is_dir() and os.path.basename(info.filename.replace("\\", "/")) == base:
                            target = info.filename
                            break
                    if target is None:
                        continue
                    data = zf.read(target)
                    out_path = os.path.join(tmp_dir, base)
                    with open(out_path, "wb") as fo:
                        fo.write(data)
                    extracted.append((base, out_path))
        elif ext in (".tar", ".tgz", ".gz", ".tar.gz") or lower.endswith((".tar", ".tgz", ".tar.gz", ".gz")):
            try:
                with tarfile.open(archive_path, "r:*") as tf:
                    safe_names = _safe_tar_names(tf)
                    for base in safe_names:
                        target = None
                        for m in tf.getmembers():
                            if m.isfile() and os.path.basename(m.name.replace("\\", "/")) == base:
                                target = m
                                break
                        if target is None:
                            continue
                        fobj = tf.extractfile(target)
                        if fobj is None:
                            continue
                        data = fobj.read()
                        out_path = os.path.join(tmp_dir, base)
                        with open(out_path, "wb") as fo:
                            fo.write(data)
                        extracted.append((base, out_path))
            except (tarfile.TarError, EOFError) as e:
                return {"success": False, "error": f"无法解压 tar 归档: {e}"}
        else:
            return {"success": False, "error": f"不支持的压缩格式 {ext}"}
    except zipfile.BadZipFile:
        return {"success": False, "error": "无效的 zip 文件"}
    except Exception as e:
        return {"success": False, "error": f"解压失败: {e}"}
    finally:
        # 清理临时目录（在移动文件之后由下方处理）
        pass

    # 限制检查 + 移动文件到用户目录并重命名
    files = []
    skipped = []
    total_size = 0
    for orig_name, src_path in extracted:
        try:
            size = os.path.getsize(src_path)
        except OSError:
            continue
        if len(files) >= MAX_FILES:
            skipped.append(orig_name + "（文件数超限）")
            try:
                os.remove(src_path)
            except OSError:
                pass
            continue
        if size > MAX_FILE_SIZE:
            skipped.append(orig_name + "（单文件超10MB）")
            try:
                os.remove(src_path)
            except OSError:
                pass
            continue
        if total_size + size > MAX_TOTAL_SIZE:
            skipped.append(orig_name + "（总体积超50MB）")
            try:
                os.remove(src_path)
            except OSError:
                pass
            continue
        total_size += size
        # 移动并重命名为唯一存储名
        stored_name = gen_filename(orig_name)
        dest_path = os.path.join(dest_root, stored_name)
        try:
            shutil.move(src_path, dest_path)
        except Exception as e:
            skipped.append(orig_name + f"（移动失败: {e}）")
            continue
        # 提取文本
        fext = os.path.splitext(orig_name)[1].lower()
        try:
            text_content = extract_text(dest_path, fext)
        except Exception as e:
            text_content = f"[解析失败: {e}]"
        files.append({
            "filename": orig_name,
            "content": text_content,
            "stored_name": stored_name,
            "size": size,
        })

    # 清理残留临时目录
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass

    return {
        "success": True,
        "stored_name": archive_name,
        "archive_path": archive_path,
        "files": files,
        "skipped": skipped,
    }


def compose_content(filename: str, result: dict) -> str:
    """把解压出的所有文件内容拼成一段完整文本，作为压缩包附件的 content 交给模型。

    解压过程完全在后台完成，前端只看到一个压缩包附件，不暴露内部文件清单。"""
    files = result.get("files", [])
    skipped = result.get("skipped", [])
    lines = [f"[压缩包 {filename} 已在后台自动解压，共 {len(files)} 个文件，内容如下：]"]
    for f in files:
        lines.append(f"\n===== 文件：{f['filename']}（{f['size']} bytes） =====")
        lines.append((f.get("content") or "").rstrip())
    if skipped:
        lines.append(f"\n[另有 {len(skipped)} 个文件因超限被跳过]")
    return "\n".join(lines)
