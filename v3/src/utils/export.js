import { marked } from 'marked'

// 字体常量
const FONT_BODY = '微软雅黑'
const FONT_CODE = 'Consolas'

// docx 模块（动态加载，避免打包进首屏主 chunk）
let docx = null

// 清理消息内容中的 HTML 换行标签，转为真正的换行（<br>、<br/>、<br />）
function normalizeContent(text) {
  if (!text) return ''
  return String(text).replace(/<br\s*\/?>/gi, '\n')
}

// 将对话消息转换为 Markdown 文本
// 角色前缀单独成行，确保消息内容中的块级 Markdown（标题/列表/代码块/表格/引用）能被正确解析
export function buildMarkdown(messages) {
  if (!Array.isArray(messages) || messages.length === 0) return ''
  const lines = []
  messages.forEach((msg) => {
    const role = msg.role
    let label = ''
    if (role === 'user') label = '我'
    else if (role === 'assistant') label = '助手'
    else if (role === 'error') label = '错误'
    else return
    lines.push(`**${label}**：`)
    lines.push('')
    lines.push(normalizeContent(msg.content))
    lines.push('')
  })
  return lines.join('\n').trim()
}

// 触发浏览器下载
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// 生成带时间戳的文件名
function timestamp() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

// 导出 Markdown 文件
export function exportMarkdown(messages) {
  const md = buildMarkdown(messages)
  if (!md) return
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  downloadBlob(blob, `对话记录_${timestamp()}.md`)
}

// ============ Markdown → docx 转换 ============

// 将嵌套行内 token 拍平为带格式的文本片段数组
function flattenInline(tokens) {
  const pieces = []
  for (const tok of tokens) {
    switch (tok.type) {
      case 'text':
        if (tok.tokens && tok.tokens.length) {
          pieces.push(...flattenInline(tok.tokens))
        } else {
          pieces.push({ text: tok.text || '' })
        }
        break
      case 'escape':
        pieces.push({ text: tok.text || '' })
        break
      case 'strong':
        pieces.push(...flattenInline(tok.tokens || []).map((p) => ({ ...p, bold: true })))
        if (!tok.tokens) pieces.push({ text: tok.text || '', bold: true })
        break
      case 'em':
        pieces.push(...flattenInline(tok.tokens || []).map((p) => ({ ...p, italics: true })))
        if (!tok.tokens) pieces.push({ text: tok.text || '', italics: true })
        break
      case 'del':
        if (tok.raw && !tok.raw.startsWith('~~')) {
          pieces.push({ text: tok.raw || tok.text || '' })
        } else {
          pieces.push(...flattenInline(tok.tokens || []).map((p) => ({ ...p, strike: true })))
          if (!tok.tokens) pieces.push({ text: tok.text || '', strike: true })
        }
        break
      case 'codespan':
        pieces.push({ text: tok.text || '', font: FONT_CODE })
        break
      case 'link':
        pieces.push({ text: tok.text || tok.href || '' })
        break
      case 'br':
        pieces.push({ text: '\n' })
        break
      case 'html':
        // 行内 HTML 标签：跳过
        break
      default:
        if (tok.text) pieces.push({ text: tok.text })
    }
  }
  return pieces
}

// 将行内 token 转换为 TextRun 数组（支持嵌套格式）
// color: 可选的文字颜色（用于引用块等）
function inlineToRuns(tokens, color) {
  const { TextRun, ShadingType } = docx
  const runs = []
  if (!Array.isArray(tokens)) return runs
  for (const tok of tokens) {
    switch (tok.type) {
      case 'text':
        if (tok.tokens && tok.tokens.length) {
          runs.push(...inlineToRuns(tok.tokens, color))
        } else {
          runs.push(new TextRun({ text: tok.text || '', font: FONT_BODY, color }))
        }
        break
      case 'escape':
        runs.push(new TextRun({ text: tok.text || '', font: FONT_BODY, color }))
        break
      case 'strong': {
        const inner = tok.tokens && tok.tokens.length ? flattenInline(tok.tokens) : [{ text: tok.text || '' }]
        for (const piece of inner) {
          runs.push(new TextRun({ text: piece.text, bold: true, italics: piece.italics, strike: piece.strike, font: piece.font || FONT_BODY, color: color }))
        }
        break
      }
      case 'em': {
        const inner = tok.tokens && tok.tokens.length ? flattenInline(tok.tokens) : [{ text: tok.text || '' }]
        for (const piece of inner) {
          runs.push(new TextRun({ text: piece.text, italics: true, bold: piece.bold, strike: piece.strike, font: piece.font || FONT_BODY, color }))
        }
        break
      }
      case 'del': {
        if (tok.raw && !tok.raw.startsWith('~~')) {
          runs.push(new TextRun({ text: tok.raw || tok.text || '', font: FONT_BODY, color }))
        } else {
          const inner = tok.tokens && tok.tokens.length ? flattenInline(tok.tokens) : [{ text: tok.text || '' }]
          for (const piece of inner) {
            runs.push(new TextRun({ text: piece.text, strike: true, bold: piece.bold, italics: piece.italics, font: piece.font || FONT_BODY, color }))
          }
        }
        break
      }
      case 'codespan':
        runs.push(new TextRun({ text: tok.text || '', font: FONT_CODE, shading: { type: ShadingType.SOLID, fill: 'F5F5F5' }, color }))
        break
      case 'link':
        runs.push(new TextRun({ text: tok.text || tok.href || '', color: '0563C1', underline: {}, font: FONT_BODY }))
        break
      case 'image':
        runs.push(new TextRun({ text: `[图片: ${tok.text || tok.href || ''}]`, italics: true, font: FONT_BODY, color }))
        break
      case 'br':
        runs.push(new TextRun({ break: 1 }))
        break
      case 'html':
        // 行内 HTML 标签（<b> 等）：跳过标签本身，内部文本由相邻 text token 承载
        break
      default:
        if (tok.text) runs.push(new TextRun({ text: tok.text, font: FONT_BODY, color }))
    }
  }
  return runs
}

// 把 block token 数组转换为 docx 子元素数组
// ctx: 段落上下文，其中 color/taskPrefix/listLevel 是自定义字段，
// 其余（indent/bullet/numbering/spacing）会合并到每个 Paragraph
function blocksToDocx(tokens, ctx = {}) {
  const { Paragraph, HeadingLevel, Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, TextRun } = docx
  const children = []
  if (!Array.isArray(tokens)) return children

  // 拆出自定义字段，剩余为 Paragraph 原生选项
  const { color, listLevel, ...paragraphOpts } = ctx

  // 渲染一个普通段落（paragraph / 块级 text / 兜底未知 token）
  const renderParagraph = (tok) => {
    const runs = inlineToRuns(tok.tokens || [], color)
    if (ctx.taskPrefix) {
      runs.unshift(new TextRun({ text: ctx.taskPrefix, font: FONT_BODY, color }))
      delete ctx.taskPrefix // 勾选框只加到该项第一个段落
    }
    children.push(new Paragraph({ children: runs, spacing: { after: 120 }, ...paragraphOpts }))
  }

  for (const tok of tokens) {
    switch (tok.type) {
      case 'heading': {
        const headingMap = {
          1: HeadingLevel.HEADING_1,
          2: HeadingLevel.HEADING_2,
          3: HeadingLevel.HEADING_3,
          4: HeadingLevel.HEADING_4,
          5: HeadingLevel.HEADING_5,
          6: HeadingLevel.HEADING_6,
        }
        children.push(new Paragraph({
          children: inlineToRuns(tok.tokens, color),
          heading: headingMap[tok.depth] || HeadingLevel.HEADING_3,
          ...paragraphOpts,
        }))
        break
      }
      case 'paragraph':
      case 'text':
        renderParagraph(tok)
        break
      case 'checkbox':
        // 任务列表勾选框由 list 分支通过 taskPrefix 处理，此处跳过
        break
      case 'html': {
        // HTML 块：剥离标签，保留可见文本
        const text = (tok.text || '').replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim()
        if (text) {
          children.push(new Paragraph({
            children: [new TextRun({ text, font: FONT_BODY, color })],
            spacing: { after: 120 },
            ...paragraphOpts,
          }))
        }
        break
      }
      case 'code': {
        const codeLines = (tok.text || '').split('\n')
        for (const line of codeLines) {
          children.push(new Paragraph({
            children: [new TextRun({ text: line || ' ', font: FONT_CODE, size: 20 })],
            shading: { type: ShadingType.SOLID, fill: 'F5F5F5' },
            spacing: { after: 0, line: 260 },
          }))
        }
        children.push(new Paragraph({ children: [], spacing: { after: 120 } }))
        break
      }
      case 'blockquote': {
        // 引用块：缩进 + 灰色文字，嵌套引用累加缩进
        const inner = blocksToDocx(tok.tokens, {
          ...ctx,
          indent: { left: (ctx.indent?.left || 0) + 360 },
          color: color || '666666',
        })
        children.push(...inner)
        break
      }
      case 'list': {
        const level = (listLevel ?? -1) + 1 // 嵌套列表递增层级
        const listCtx = tok.ordered
          ? { numbering: { reference: 'ordered-list', level: Math.min(level, 2) }, listLevel: level }
          : { bullet: { level: Math.min(level, 8) }, listLevel: level }
        for (const item of tok.items) {
          const itemCtx = { ...ctx, ...listCtx, spacing: { after: 60 } }
          if (item.task) itemCtx.taskPrefix = item.checked ? '☑ ' : '☐ '
          const itemTokens = (item.tokens || []).filter((t) => t.type !== 'checkbox')
          children.push(...blocksToDocx(itemTokens, itemCtx))
        }
        break
      }
      case 'table': {
        const borders = {
          top: { style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' },
          bottom: { style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' },
          left: { style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' },
          right: { style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' },
          insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' },
          insideVertical: { style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' },
        }
        const rows = []
        rows.push(new TableRow({
          tableHeader: true,
          children: (tok.header || []).map((cell) => new TableCell({
            children: [new Paragraph({ children: inlineToRuns(cell.tokens), alignment: 'center' })],
            shading: { type: ShadingType.SOLID, fill: 'EEEEEE' },
          })),
        }))
        for (const row of tok.rows || []) {
          rows.push(new TableRow({
            children: row.map((cell) => new TableCell({
              children: [new Paragraph({ children: inlineToRuns(cell.tokens) })],
            })),
          }))
        }
        children.push(new Table({ rows, borders, width: { size: 100, type: WidthType.PERCENTAGE } }))
        children.push(new Paragraph({ children: [], spacing: { after: 120 } }))
        break
      }
      case 'hr':
        children.push(new Paragraph({
          children: [new TextRun({ text: '' })],
          border: { bottom: { style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC', space: 1 } },
          spacing: { after: 120 },
        }))
        break
      case 'space':
        break
      default:
        // 未知块级 token 兜底：尽量保留文本内容，不丢东西
        if (Array.isArray(tok.tokens) && tok.tokens.length) {
          renderParagraph(tok)
        } else if (tok.text) {
          children.push(new Paragraph({
            children: [new TextRun({ text: String(tok.text), font: FONT_BODY, color })],
            spacing: { after: 120 },
            ...paragraphOpts,
          }))
        }
        break
    }
  }
  return children
}

// 导出 Word 文件（使用 docx 库生成真正的 .docx）
export async function exportWord(messages) {
  const md = buildMarkdown(messages)
  if (!md) return
  try {
    // 动态加载 docx，避免打包进首屏主 chunk
    if (!docx) {
      docx = await import('docx')
    }
    const { Document, Packer } = docx

    // 用 marked 的 lexer 解析为 token（复用已配置的 marked，含单波浪号修复）
    const tokens = marked.lexer(md)
    const children = blocksToDocx(tokens)

    const doc = new Document({
      creator: '个人助理',
      title: '对话记录',
      numbering: {
        config: [
          {
            reference: 'ordered-list',
            levels: [0, 1, 2].map((i) => ({
              level: i,
              format: 'decimal',
              text: `%${i + 1}.`,
              alignment: 'start',
            })),
          },
        ],
      },
      styles: {
        default: {
          document: { run: { font: FONT_BODY, size: 22 } },
        },
      },
      sections: [{
        properties: {},
        children,
      }],
    })

    const blob = await Packer.toBlob(doc)
    downloadBlob(blob, `对话记录_${timestamp()}.docx`)
  } catch (err) {
    console.error('导出 Word 失败:', err)
    alert('导出 Word 失败：' + (err.message || err))
  }
}

// 导出图片（截取消息区域完整内容）
export async function exportImage(container, filename) {
  if (!container) return
  try {
    const html2canvas = (await import('html2canvas')).default

    // 克隆容器并展开为完整高度，避免 overflow 只截取可视区域
    const clone = container.cloneNode(true)
    clone.style.position = 'fixed'
    clone.style.left = '-99999px'
    clone.style.top = '0'
    clone.style.width = container.scrollWidth + 'px'
    clone.style.height = 'auto'
    clone.style.maxHeight = 'none'
    clone.style.overflow = 'visible'
    const computed = window.getComputedStyle(container)
    clone.style.padding = computed.padding
    clone.style.background = computed.backgroundColor
    clone.style.color = computed.color
    clone.style.fontFamily = computed.fontFamily
    document.body.appendChild(clone)

    try {
      const canvas = await html2canvas(clone, {
        backgroundColor: computed.backgroundColor || '#ffffff',
        scale: Math.min(window.devicePixelRatio || 1, 2),
        useCORS: true,
        logging: false,
        windowWidth: container.scrollWidth,
      })
      const dataUrl = canvas.toDataURL('image/png')
      const a = document.createElement('a')
      a.href = dataUrl
      a.download = filename || `对话记录_${timestamp()}.png`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    } finally {
      document.body.removeChild(clone)
    }
  } catch (err) {
    console.error('导出图片失败:', err)
    alert('导出图片失败：' + (err.message || err))
  }
}
