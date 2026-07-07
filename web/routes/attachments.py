import os
from fastapi import APIRouter, Request, Depends, File, UploadFile
from utils.logger import logger

router = APIRouter()


def get_managers(request: Request):
    return request.app.state.managers


@router.post("/attachments/upload")
async def upload_attachment(file: UploadFile = File(...), managers: dict = Depends(get_managers)):
    """上传附件"""
    attachment_manager = managers["attachment_manager"]
    try:
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)

        filepath = os.path.join(upload_dir, file.filename)
        content = await file.read()
        with open(filepath, 'wb') as f:
            f.write(content)

        attachment_manager.add_attachment(filepath)
        return {"status": "success", "message": "附件上传成功", "filename": file.filename}
    except Exception as e:
        return {"status": "error", "message": f"上传失败: {str(e)}"}


@router.get("/attachments")
async def get_attachments(managers: dict = Depends(get_managers)):
    """获取所有附件"""
    attachment_manager = managers["attachment_manager"]
    attachments = attachment_manager.get_attachments()
    return [att.filename for att in attachments]


@router.delete("/attachments/{filename}")
async def delete_attachment(filename: str, managers: dict = Depends(get_managers)):
    """删除附件"""
    attachment_manager = managers["attachment_manager"]
    attachments = attachment_manager.get_attachments()
    for att in attachments:
        if att.filename == filename:
            attachment_manager.remove_attachment(att.id)
            return {"status": "success", "message": "附件删除成功"}
    return {"status": "error", "message": "附件不存在"}


@router.post("/attachments/clear")
async def clear_attachments(managers: dict = Depends(get_managers)):
    """清空所有附件"""
    attachment_manager = managers["attachment_manager"]
    attachment_manager.clear()
    return {"status": "success", "message": "已清空所有附件"}
