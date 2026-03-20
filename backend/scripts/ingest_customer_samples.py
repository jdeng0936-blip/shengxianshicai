"""
客户样本规程入库脚本 — 将客户提交的真实规程文件解析后写入知识库

用法: python scripts/ingest_customer_samples.py

支持格式: .docx（python-docx直接读取）、.doc（textutil转换后读取）

功能:
  1. 扫描指定列表的客户规程文件
  2. 提取全文文本，按章节切分
  3. 写入 std_document + std_clause 表，doc_type = '客户样本'
  4. 为后续 AI vs 人工对比提供基准数据
"""
import asyncio
import os
import re
import subprocess
import sys
import tempfile

# 让脚本能 import app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


# ========== 文件读取 ==========

def read_docx(file_path: str) -> str:
    """读取 .docx 文件全文"""
    from docx import Document
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def read_doc(file_path: str) -> str:
    """读取 .doc 文件 — macOS 用 textutil 转换后读取"""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        subprocess.run(
            ["textutil", "-convert", "txt", "-output", tmp_path, file_path],
            check=True, capture_output=True
        )
        with open(tmp_path, "r", encoding="utf-8") as f:
            return f.read()
    except subprocess.CalledProcessError as e:
        print(f"  textutil 转换失败: {e}")
        return ""
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def read_file(file_path: str) -> str:
    """根据文件类型选择读取方式"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".docx":
        return read_docx(file_path)
    elif ext == ".doc":
        return read_doc(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")


# ========== 章节切分 ==========

RE_CHAPTER = re.compile(r'^第([一二三四五六七八九十百]+)章\s*(.*)')
RE_SECTION = re.compile(r'^第([一二三四五六七八九十百]+)节\s*(.*)')
RE_ITEM = re.compile(r'^([一二三四五六七八九十]+)、\s*(.*)')


def sanitize_text(s: str) -> str:
    """清洗文本：移除 0x00 和控制字符"""
    s = s.replace('\x00', '')
    s = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f]', '', s)
    return s.strip()


def parse_chapters(text: str, doc_title: str) -> list[dict]:
    """按章节切分文本"""
    lines = text.splitlines()
    clauses: list[dict] = []
    cur_chapter = ""
    cur_section = ""
    cur_clause: dict | None = None

    def flush():
        nonlocal cur_clause
        if cur_clause and len(cur_clause["content"].strip()) > 10:
            cur_clause["content"] = sanitize_text(cur_clause["content"])
            cur_clause["title"] = sanitize_text(cur_clause["title"])
            clauses.append(cur_clause)
        cur_clause = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 章级
        m = RE_CHAPTER.match(line)
        if m:
            flush()
            cur_chapter = f"第{m.group(1)}章 {m.group(2).strip()}"
            cur_section = ""
            cur_clause = {
                "clause_no": f"第{m.group(1)}章",
                "title": cur_chapter,
                "content": "",
                "level": 1,
            }
            continue

        # 节级
        m = RE_SECTION.match(line)
        if m:
            flush()
            cur_section = f"第{m.group(1)}节 {m.group(2).strip()}"
            hierarchy = " > ".join(p for p in [cur_chapter, cur_section] if p)
            cur_clause = {
                "clause_no": f"第{m.group(1)}节",
                "title": hierarchy,
                "content": "",
                "level": 2,
            }
            continue

        # 大条目 (一、二、三、)
        m = RE_ITEM.match(line)
        if m and len(line) > 5:
            flush()
            hierarchy = " > ".join(p for p in [cur_chapter, cur_section] if p)
            cur_clause = {
                "clause_no": f"{m.group(1)}",
                "title": hierarchy + (f" > {m.group(2).strip()}" if m.group(2).strip() else ""),
                "content": line + "\n",
                "level": 3,
            }
            continue

        # 正文追加
        if cur_clause:
            cur_clause["content"] += line + "\n"
        else:
            if len(line) > 15:
                cur_clause = {
                    "clause_no": "概述",
                    "title": doc_title,
                    "content": line + "\n",
                    "level": 0,
                }

    flush()
    return clauses


# ========== 客户规程文件列表 ==========

SAMPLE_FILES = [
    {
        "path": "/Users/mac111/Desktop/煤炭/15314进风巷规程文字部分1.25(1).doc",
        "title": "15314进风巷掘进作业规程",
    },
    {
        "path": "/Users/mac111/Desktop/煤炭/15404规程.doc",
        "title": "15404工作面掘进作业规程",
    },
    {
        "path": "/Users/mac111/Desktop/煤炭/470水平大巷运输作业规程（二矿大巷运输队）.docx",
        "title": "470水平大巷运输作业规程",
    },
]


async def main():
    from sqlalchemy import text
    from app.core.database import engine

    total_clauses = 0

    async with engine.begin() as conn:
        for sample in SAMPLE_FILES:
            if not os.path.exists(sample["path"]):
                print(f"❌ 文件不存在: {sample['path']}")
                continue

            print(f"\n{'='*60}")
            print(f"📄 处理: {sample['title']}")
            print(f"   文件: {os.path.basename(sample['path'])}")

            # 读取文本
            try:
                full_text = read_file(sample["path"])
            except Exception as e:
                print(f"   ❌ 读取失败: {e}")
                continue

            print(f"   全文长度: {len(full_text)} 字符")

            # 解析章节
            clauses = parse_chapters(full_text, sample["title"])
            print(f"   解析条款: {len(clauses)} 条")

            if not clauses:
                print("   ⚠️ 未解析到有效条款，跳过")
                continue

            # 预览前5条
            for i, c in enumerate(clauses[:5]):
                print(f"   [{i+1}] {c['clause_no']} | {c['title'][:40]} | {c['content'][:50].strip()}")

            # 检查是否已录入
            existing = (await conn.execute(text(
                "SELECT id FROM std_document WHERE title = :title AND doc_type = '客户样本'"
            ), {"title": sample["title"]})).fetchone()

            if existing:
                doc_id = existing[0]
                del_count = (await conn.execute(text(
                    "DELETE FROM std_clause WHERE document_id = :did"
                ), {"did": doc_id})).rowcount
                print(f"   🔄 已删除旧条款 {del_count} 条，重新录入...")
            else:
                result = await conn.execute(text(
                    "INSERT INTO std_document (title, doc_type, version, is_current, tenant_id) "
                    "VALUES (:title, :doc_type, :version, :is_current, :tenant_id) RETURNING id"
                ), {
                    "title": sample["title"],
                    "doc_type": "客户样本",
                    "version": "v1.0",
                    "is_current": True,
                    "tenant_id": 0,
                })
                doc_id = result.fetchone()[0]
                print(f"   ✅ 创建文档记录: id={doc_id}")

            # 批量插入条款
            inserted = 0
            for c in clauses:
                # 截断至数据库字段长度限制
                title_truncated = c["title"][:195] + "..." if len(c["title"]) > 200 else c["title"]
                clause_no_truncated = c["clause_no"][:50] if len(c["clause_no"]) > 50 else c["clause_no"]
                await conn.execute(text(
                    "INSERT INTO std_clause (document_id, clause_no, title, content, level) "
                    "VALUES (:doc_id, :clause_no, :title, :content, :level)"
                ), {
                    "doc_id": doc_id,
                    "clause_no": clause_no_truncated,
                    "title": title_truncated,
                    "content": c["content"],
                    "level": c["level"],
                })
                inserted += 1

            print(f"   🎉 入库: {inserted} 条（doc_id={doc_id}, doc_type=客户样本）")
            total_clauses += inserted

    print(f"\n{'='*60}")
    print(f"📊 总计入库: {total_clauses} 条客户样本条款")
    print(f"⏭️  下一步: python scripts/vectorize_clauses.py 完成向量化")


if __name__ == "__main__":
    asyncio.run(main())
