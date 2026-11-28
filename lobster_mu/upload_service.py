# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 文件上传与文本提取（按 user_id 隔离存储）"""
import os
import json
from datetime import datetime

from lobster_mu.paths import uploads_dir, gen_filename

# 10MB 上传限制
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

# 按扩展名分类：返回用于模型的简短说明文本（文件本身已落盘，不在此做二次处理）
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".svg", ".heic"}
_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".3gp", ".mpeg", ".mpg"}
_AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma"}
_BINARY_EXT = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".iso", ".exe", ".msi", ".apk", ".dmg"}

# 可自动解压的压缩格式（archive_service 处理；.rar/.7z 不在内）
_ARCHIVE_EXT = {".zip", ".tar", ".tgz", ".gz"}


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _is_garbled(text: str) -> bool:
    """检测文本是否为乱码（PDF 提取常见问题）。

    只抓真正的编码损坏（U+FFFD、连续 ? 占位符、高比例不可打印字符），
    不做容易误伤正常中文文档的「字符多样性」硬判定。
    """
    if not text or not text.strip():
        return True
    chars = [c for c in text if c.isprintable() or c in '\n\r\t']
    if not chars:
        return True
    replacement_ratio = sum(1 for c in text if c == '\ufffd') / len(text)
    if replacement_ratio > 0.05:
        return True
    printable_ratio = len(chars) / len(text)
    if printable_ratio < 0.5:
        return True
    import re
    q_runs = re.findall(r'\?{2,}', text)
    q_count = sum(len(r) for r in q_runs)
    if q_count / max(len(text), 1) > 0.10:
        return True
    # CJK 正文天然字符重复率高（的/是/在/一 等高频字反复出现），
    # 不能用 unique_ratio 这种只适用于英文的硬阈值。
    # 只有在 CJK 占比很低（疑似 ASCII 为主但又缺字符）时才检查多样性。
    cjk = sum(1 for c in chars if '\u4e00' <= c <= '\u9fff')
    cjk_ratio = cjk / max(len(chars), 1)
    if cjk_ratio < 0.2:
        content_chars = [c for c in chars if not c.isspace()]
        if content_chars:
            unique_ratio = len(set(content_chars)) / len(content_chars)
            if unique_ratio < 0.10:
                return True
    # ASCII 可见字符占比极低且无 CJK，意味着大概率是二进制/损坏编码
    ascii_visible = sum(1 for c in chars if c.isascii() and c.isprintable())
    if ascii_visible / max(len(chars), 1) < 0.05 and cjk_ratio < 0.1:
        return True
    return False


def extract_text(file_path: str, ext: str, raw: bytes = None) -> str:
    """按扩展名提取文本内容（复制自原版逻辑）"""
    if ext in ['.txt', '.md', '.json', '.py', '.js', '.html', '.css', '.xml', '.csv']:
        if raw is not None:
            return raw.decode('utf-8', errors='replace')
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    if ext in ['.doc', '.docx']:
        try:
            from docx import Document
            doc = Document(file_path)
            return '\n'.join([para.text for para in doc.paragraphs])
        except ImportError:
            return "[需要安装 python-docx 库来解析Word文档]"
        except Exception as e:
            return f"[解析Word文档失败: {str(e)}]"
    if ext == '.pdf':
        try:
            try:
                import pymupdf
            except ImportError:
                import fitz as pymupdf
            doc = pymupdf.open(file_path)
            text = '\n'.join([page.get_text() for page in doc])
            # 直接提取的文本若已乱码，立即拒绝（不再尝试 OCR）
            if _is_garbled(text):
                raise ValueError("PDF 文本提取结果异常（疑似乱码），已拒绝入库。请确认 PDF 文字层编码正确（常见于扫描件误存为可提取 PDF 或编码损坏）。")
            # 文本过少（可能是扫描件）时尝试 OCR 回退
            if len(text.strip()) < 100:
                try:
                    import pytesseract
                    from PIL import Image
                    ocr_text = ""
                    for page in doc:
                        pix = page.get_pixmap()
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        ocr_text += pytesseract.image_to_string(img, lang='chi_sim') + '\n'
                    text = ocr_text
                    if _is_garbled(text):
                        raise ValueError("PDF OCR 结果异常（疑似乱码），已拒绝入库。请确认 PDF 文字层编码正确，或转换为图片 PDF 后重试。")
                except ImportError:
                    # OCR 库未安装：无法对扫描件回退识别。
                    # 正常短文档（已含可提取文本）放行；真正的空文档已被上方 _is_garbled 拦截。
                    pass
            return text
        except ImportError:
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(file_path)
                return '\n'.join([page.extract_text() or '' for page in reader.pages])
            except ImportError:
                return "[需要安装 PyMuPDF(fitz) 或 PyPDF2 库来解析PDF文档]"
            except Exception as e:
                return f"[使用PyPDF2解析PDF失败: {str(e)}]"
        except ValueError:
            # 乱码检测抛出的 ValueError 向上传递，让上传路由捕获并返回 success=False
            raise
        except Exception as e:
            return f"[解析PDF文档失败: {str(e)}]"
    if ext in ['.xls', '.xlsx']:
        try:
            from utils.excel_reader import read_excel_text
            return read_excel_text(file_path)
        except ImportError:
            return "[需要安装 openpyxl 库解析 .xlsx（旧版 .xls 需 xlrd）]"
        except Exception as e:
            return f"[解析Excel文件失败: {str(e)}]"
    if ext in ['.ppt', '.pptx']:
        try:
            from pptx import Presentation
            prs = Presentation(file_path)
            text = ''
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, 'text'):
                        text += shape.text + '\n'
            return text
        except ImportError:
            return "[需要安装 python-pptx 库来解析PowerPoint文件]"
        except Exception as e:
            return f"[解析PowerPoint文件失败: {str(e)}]"
    # 以下类型无法提取文本：返回简短说明，让模型知道文件性质。
    # 文件本身已落盘并以附件形式挂载到会话，前端按 MIME 自行渲染/下载。
    if ext in _IMAGE_EXT:
        return f"[已上传图片文件 {ext}：二进制图片数据，已作为附件挂载，请直接查看图片或描述图像内容]"
    if ext in _VIDEO_EXT:
        return f"[已上传视频文件 {ext}：二进制视频数据，已作为附件挂载，请直接播放视频或描述视频内容]"
    if ext in _AUDIO_EXT:
        return f"[已上传音频文件 {ext}：二进制音频数据，已作为附件挂载，请直接播放音频]"
    if ext in _BINARY_EXT:
        return f"[已上传二进制/压缩文件 {ext}：无法提取文本，已作为附件挂载请直接下载解压]"
    return f"[不支持提取文本的文件类型 {ext}：已作为附件挂载]"


def save_upload(user_id: int, filename: str, content: bytes) -> dict:
    """保存上传文件到用户目录并提取文本，返回文件信息。

    压缩包（.zip/.tar/.tgz/.gz）会在后台自动解压：path 指向压缩包本身，
    content 为所有内部文件拼接后的完整文本（对前端只呈现为一个附件）。"""
    ext = os.path.splitext(filename or "")[1][:16].lower()
    target_dir = uploads_dir(user_id)
    unique_name = gen_filename(filename)
    file_path = os.path.join(target_dir, unique_name)
    with open(file_path, 'wb') as f:
        f.write(content)

    # 压缩包分支：延迟导入避免循环（archive_service 依赖本模块 extract_text）
    if ext in _ARCHIVE_EXT:
        from lobster_mu import archive_service
        result = archive_service.process_archive_from_path(user_id, filename, content, file_path)
        if result.get("success"):
            return {
                "filename": filename,
                "path": file_path,
                "size": len(content),
                "content": archive_service.compose_content(filename, result),
                "timestamp": _now(),
            }
        # 解压失败：回退为普通二进制文件提示
        text_content = extract_text(file_path, ext, raw=content)
        return {
            "filename": filename,
            "path": file_path,
            "size": len(content),
            "content": text_content,
            "timestamp": _now(),
        }

    text_content = extract_text(file_path, ext, raw=content)
    return {
        "filename": filename,
        "path": file_path,
        "size": len(content),
        "content": text_content,
        "timestamp": _now(),
    }


def save_upload_text(user_id: int, filename: str, content: bytes) -> dict:
    """上传并返回解析文本（v2 前端 /upload/text 使用）。

    同时返回 stored_name/size，供会话消息记录原始文件引用（历史会话可再次打开/下载）。"""
    ext = os.path.splitext(filename or "")[1][:16].lower()
    target_dir = uploads_dir(user_id)
    unique_name = gen_filename(filename)
    file_path = os.path.join(target_dir, unique_name)
    with open(file_path, 'wb') as f:
        f.write(content)
    print(f"[DEBUG] mu上传文件: {filename}, 大小: {len(content)} bytes, 扩展名: {ext}")
    print(f"[DEBUG] mu文件已保存到: {file_path}")

    # 压缩包分支：后台解压，content 为内部文件拼接后的完整文本（前端只呈现压缩包本身）
    if ext in _ARCHIVE_EXT:
        from lobster_mu import archive_service
        result = archive_service.process_archive_from_path(user_id, filename, content, file_path, unique_name)
        if result.get("success"):
            return {"success": True, "filename": filename,
                    "content": archive_service.compose_content(filename, result),
                    "stored_name": unique_name, "size": len(content)}
        # 解压失败：回退普通提示
        text_content = extract_text(file_path, ext, raw=content)
        return {"success": True, "filename": filename, "content": text_content,
                "stored_name": unique_name, "size": len(content)}

    text_content = extract_text(file_path, ext, raw=content)
    print(f"[DEBUG] mu解析内容长度: {len(text_content)}")
    return {"success": True, "filename": filename, "content": text_content,
            "stored_name": unique_name, "size": len(content)}
