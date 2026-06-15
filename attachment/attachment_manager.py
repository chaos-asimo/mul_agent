"""Attachment manager for handling file attachments"""
import os
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


@dataclass
class Attachment:
    """Represents a file attachment"""
    id: str
    filename: str
    filepath: str
    file_type: str  # 'docx', 'pdf', 'txt'
    content: str = ""

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]


class AttachmentManager:
    """Manages file attachments"""

    SUPPORTED_TYPES = {
        '.docx': 'docx',
        '.pdf': 'pdf',
        '.txt': 'txt'
    }

    def __init__(self):
        self.attachments: List[Attachment] = []

    def add_attachment(self, filepath: str) -> Optional[Attachment]:
        """Add a new attachment from file path"""
        if not os.path.exists(filepath):
            return None

        ext = os.path.splitext(filepath)[1].lower()
        if ext not in self.SUPPORTED_TYPES:
            return None

        attachment = Attachment(
            id="",
            filename=os.path.basename(filepath),
            filepath=filepath,
            file_type=self.SUPPORTED_TYPES[ext]
        )

        # Extract content based on file type
        if attachment.file_type == 'docx':
            attachment.content = self._extract_docx(filepath)
        elif attachment.file_type == 'pdf':
            attachment.content = self._extract_pdf(filepath)
        elif attachment.file_type == 'txt':
            attachment.content = self._read_txt(filepath)

        self.attachments.append(attachment)
        return attachment

    def _extract_docx(self, filepath: str) -> str:
        """Extract text from Word document"""
        try:
            from docx import Document
            doc = Document(filepath)
            paragraphs = []
            for para in doc.paragraphs:
                if para.text.strip():
                    paragraphs.append(para.text)
            return '\n'.join(paragraphs)
        except ImportError:
            return f"[无法提取Word文档内容，请安装python-docx库] 文件: {filepath}"
        except Exception as e:
            return f"[Word文档提取失败] {str(e)}"

    def _extract_pdf(self, filepath: str) -> str:
        """Extract text from PDF document"""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(filepath)
            text_parts = []
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
            doc.close()
            return '\n'.join(text_parts)
        except ImportError:
            try:
                import PyPDF2
                with open(filepath, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text_parts = []
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                    return '\n'.join(text_parts)
            except ImportError:
                return f"[无法提取PDF内容，请安装PyMuPDF或PyPDF2库] 文件: {filepath}"
            except Exception as e:
                return f"[PDF提取失败] {str(e)}"
        except Exception as e:
            return f"[PDF提取失败] {str(e)}"

    def _read_txt(self, filepath: str) -> str:
        """Read text file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(filepath, 'r', encoding='gbk') as f:
                    return f.read()
            except Exception as e:
                return f"[文本文件读取失败] {str(e)}"

    def remove_attachment(self, attachment_id: str) -> bool:
        """Remove an attachment by ID"""
        for i, att in enumerate(self.attachments):
            if att.id == attachment_id:
                del self.attachments[i]
                return True
        return False

    def get_all_content(self) -> str:
        """Get combined content of all attachments"""
        if not self.attachments:
            return ""

        contents = []
        for att in self.attachments:
            contents.append(f"\n===== 附件: {att.filename} =====\n")
            contents.append(att.content)

        return '\n'.join(contents)

    def clear(self):
        """Clear all attachments"""
        self.attachments.clear()

    def get_attachments(self) -> List[Attachment]:
        """Get list of all attachments"""
        return self.attachments.copy()
