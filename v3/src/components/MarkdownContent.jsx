import { useMemo, useRef, useEffect } from 'react'
import { marked } from 'marked'
import { highlightPythonCode, escapeHtml } from '../utils/highlight'
import katex from 'katex'
import 'katex/dist/katex.min.css'

marked.setOptions({ gfm: true, breaks: true })

// 自定义代码块渲染：Python（含未指定语言）代码块做关键字高亮，与 v1 能力一致
const renderer = new marked.Renderer()
renderer.code = ({ text, lang }) => {
  const language = (lang || '').toLowerCase()
  const isPy = !language || language === 'python' || language === 'py'
  const inner = isPy ? highlightPythonCode(text) : escapeHtml(text)
  const cls = isPy ? 'python-highlight' : ''
  return `<pre><code${cls ? ` class="${cls}"` : ''}>${inner}</code></pre>`
}
// marked GFM 的删除线会把单个 ~text~ 也解析为 <del>，但标准 GFM 只认 ~~text~~。
// 用 walkTokens 把单波浪号的 del 还原为普通文本，避免 "1~10"、"a~b" 等被误渲染。
marked.use({
  renderer,
  walkTokens(token) {
    if (token.type === 'del' && token.raw && !token.raw.startsWith('~~')) {
      token.type = 'text'
      token.text = token.raw
      delete token.tokens
    }
  },
})

// breaks:true 模式下行内空格本来就会被吞，预处理去掉每行行首空白不影响行内排版。
// 但能恢复 marked 的"左起加粗"规则：`**xxx**` 不再因前面有换行/空格而被判定为
// 未闭合内联标记而原样输出（如文档里 `**涌现（Emergence）**` 这种加粗）。
function normalizeInlineBreaks(src) {
  return String(src).replace(/[ \t]+(\r?\n)/g, '$1').replace(/^[ \t]+/gm, '')
}

// 去掉 URL 末尾误并入的标点（中英文括号/句号/逗号/分号/感叹问号等，含其百分号编码）
const TRAIL_PUNCT = /(?:[。．.，,；;！!？?）)】」』]|%E3%80%82|%EF%BC%8E|%EF%BC%8C|%EF%BC%9B|%EF%BC%81|%EF%BC%9F|%EF%BC%89|%29|%2C|%3B|%21|%3F|%5D)+$/i
function cleanUrl(u) {
  let cur = String(u || '')
  let prev
  do { prev = cur; cur = cur.replace(TRAIL_PUNCT, '') } while (cur !== prev)
  return cur
}

// 桌面浏览器用新标签页打开链接；移动端/WebView 下在当前窗口导航，
// 使其进入 WebView 历史栈，系统返回键可回到原页面（target=_blank 会脱离返回栈）。
const OPEN_IN_NEW_TAB = typeof navigator !== 'undefined'
  && !/Android|iPhone|iPad|iPod|Mobile|HarmonyOS|WebView|MicroMessenger|wxwork/i.test(navigator.userAgent || '')

// 给所有 <a> 注入链接属性，并清洗 href 尾部标点（不改文本，保证显示与跳转一致）
function sanitizeAnchors(html) {
  const targetAttr = OPEN_IN_NEW_TAB
    ? ' target="_blank" rel="noopener noreferrer"'
    : ' target="_self"'
  return String(html).replace(/<a\b([^>]*?)\shref="([^"]*)"/gi, (m, attrs, url) => {
    const clean = cleanUrl(url)
    return `<a${targetAttr}${attrs} href="${clean}"`
  })
}

// ---- KaTeX 数学公式处理（占位符方案）----
// 思路：marked.parse 之前把 LaTeX 公式替换成特殊占位符（marked 不会修改），
// 解析 HTML 后再把占位符替换回 KaTeX 渲染的 HTML。这样能绕过 marked 对
// $$ 拆分、\\ 转义、\begin 等字符的破坏。
// 占位符形如 ⟦M0⟧、⟦M1⟧（U+27E6/U+27E7 是数学括号，markdown 不识别）。

const MATH_PLACEHOLDER = /⟦M(\d+)⟧/g

function extractMath(src) {
  const mathStore = []
  let out = ''
  let i = 0
  const len = src.length

  function isCodeFenceBefore(idx) {
    // 检查 idx 之前行首 ``` 数量为偶数（偶数=不在围栏代码块内）
    const before = src.slice(0, idx)
    const fences = (before.match(/^```/gm) || []).length
    return fences % 2 === 0
  }
  function isInsideInlineCode(idx) {
    // 检查 idx 处是否位于行内代码 `...` 内部。
    // 算法：从 idx 向前扫描到行首，统计反引号数量；
    // 若遇到奇数个反引号（即处于打开状态），说明在行内代码内。
    // 只考虑当前行（\n 之前的部分）。
    const lineStart = src.lastIndexOf('\n', idx - 1) + 1
    const before = src.slice(lineStart, idx)
    const ticks = (before.match(/`/g) || []).length
    return ticks % 2 === 1
  }

  while (i < len) {
    const ch = src[i]
    if (ch === '$') {
      // 尝试匹配 $$ 或 $
      if (src[i + 1] === '$') {
        // 块级公式：$$...$$（可跨行）
        const closeIdx = src.indexOf('$$', i + 2)
        if (closeIdx !== -1) {
          const tex = src.slice(i + 2, closeIdx)
          // 防止匹配围栏代码块或行内代码内的 $$
          if (isCodeFenceBefore(i) && !isInsideInlineCode(i)) {
            mathStore.push({ tex, display: true })
            out += `⟦M${mathStore.length - 1}⟧`
            i = closeIdx + 2
            continue
          }
        }
      } else {
        // 行内公式：$...$（不跨行）
        const lineEnd = src.indexOf('\n', i + 1)
        const searchEnd = lineEnd === -1 ? len : lineEnd
        const closeIdx = src.indexOf('$', i + 1)
        if (closeIdx !== -1 && closeIdx < searchEnd) {
          const tex = src.slice(i + 1, closeIdx)
          // 防误判金额：tex 前后是数字则跳过
          const beforeChar = i > 0 ? src[i - 1] : ''
          const afterChar = closeIdx + 1 < len ? src[closeIdx + 1] : ''
          const isAmount = /\d/.test(beforeChar) || /\d/.test(afterChar)
          // 必须包含合法 LaTeX 内容（不能是空或纯空白）
          const isEmpty = tex.trim() === ''
          if (!isAmount && !isEmpty && isCodeFenceBefore(i) && !isInsideInlineCode(i)) {
            mathStore.push({ tex, display: false })
            out += `⟦M${mathStore.length - 1}⟧`
            i = closeIdx + 1
            continue
          }
        }
      }
    }
    out += ch
    i++
  }
  return { out, mathStore }
}

function renderMathInHtml(html, mathStore) {
  // 把 HTML 中的占位符替换回 KaTeX 渲染的 HTML
  return html.replace(MATH_PLACEHOLDER, (_, idxStr) => {
    const idx = parseInt(idxStr, 10)
    const item = mathStore[idx]
    if (!item) return `⟦M${idx}⟧`
    try {
      return katex.renderToString(item.tex, {
        displayMode: item.display,
        throwOnError: false,
        strict: false,
        trust: false,
      })
    } catch {
      return item.display
        ? `<div class="math-fallback">${escapeHtml(item.tex)}</div>`
        : `<span class="math-fallback">${escapeHtml(item.tex)}</span>`
    }
  })
}

// 修补 marked 漏渲染的加粗。
// marked 的强调判定不把中文标点（如“。”）当作标点，遇到
// “**5．业务承载与结果返回。**紧接中文” 这种“闭合 ** 紧贴非空白字符”的写法
// 会判定无法闭合而原样输出 **。这里把渲染结果中残留的 **文字** 补成 <strong>，
// 同时跳过 <pre>/<code> 代码区域，避免误伤代码里的 ** 符号。
function fixLiteralBold(html) {
  const parts = String(html || '').split(/(<pre[\s\S]*?<\/pre>|<code[\s\S]*?<\/code>)/g)
  for (let i = 0; i < parts.length; i += 2) {
    parts[i] = parts[i].replace(/\*\*([^<]*?)\*\*/g, '<strong>$1</strong>')
  }
  return parts.join('')
}

// ---- ASCII 框线表格对齐 ----
// 模型输出的框线表格常按"字符个数"补齐，但中文/全角字符占 2 个显示列导致右边框错位。
// 这里按显示宽度重算各列并补齐；未包在代码围栏内的框线块转成 ```text 围栏，
// 由 marked 渲染为 <pre> 以保留空格。
function displayWidth(text) {
  let w = 0
  for (const ch of String(text || '')) {
    const code = ch.codePointAt(0)
    if ((code >= 0x0300 && code <= 0x036f) || code === 0x200b) continue
    const wide =
      (code >= 0x1100 && code <= 0x115f) ||
      code === 0x2329 || code === 0x232a ||
      (code >= 0x2e80 && code <= 0xa4cf) ||
      (code >= 0xac00 && code <= 0xd7a3) ||
      (code >= 0xf900 && code <= 0xfaff) ||
      (code >= 0xfe10 && code <= 0xfe19) ||
      (code >= 0xfe30 && code <= 0xfe6f) ||
      (code >= 0xff00 && code <= 0xff60) ||
      (code >= 0xffe0 && code <= 0xffe6) ||
      (code >= 0x1f300 && code <= 0x1f64f) ||
      (code >= 0x1f900 && code <= 0x1f9ff) ||
      (code >= 0x20000 && code <= 0x3fffd)
    w += wide ? 2 : 1
  }
  return w
}

const isBoxLine = (line) => /[│┌┐└┘├┤┬┴┼]/.test(line)

function alignBoxBlock(lines) {
  const cells = []
  let colCount = 0
  lines.forEach((line) => {
    const t = line.trim()
    if (/^│.*│$/.test(t)) {
      const parts = t.slice(1, -1).split('│').map((p) => p.replace(/\s+$/, ''))
      colCount = Math.max(colCount, parts.length)
      cells.push(parts)
    } else {
      cells.push(null)
    }
  })
  if (colCount === 0) return lines

  const widths = new Array(colCount).fill(0)
  cells.forEach((parts) => {
    if (!parts) return
    for (let c = 0; c < parts.length; c++) {
      widths[c] = Math.max(widths[c], displayWidth(parts[c]))
    }
  })

  const junction = { '┌': '┬', '├': '┼', '└': '┴' }
  return lines.map((line, idx) => {
    const t = line.trim()
    const parts = cells[idx]
    if (parts) {
      const padded = []
      for (let c = 0; c < colCount; c++) {
        const cell = parts[c] || ''
        const diff = widths[c] - displayWidth(cell)
        padded.push(diff > 0 ? cell + ' '.repeat(diff) : cell)
      }
      return '│' + padded.join('│') + '│'
    }
    const border = t.match(/([┌├└])([─┬┴┼]+)([┐┤┘])/)
    if (border && junction[border[1]]) {
      return border[1] + widths.map((w) => '─'.repeat(w)).join(junction[border[1]]) + border[3]
    }
    return line
  })
}

// 单列框线块 -> HTML 表格（CSS 边框绘制，彻底避免字体宽度导致错位）；
// 多列/复杂图示返回空字符串，交给 <pre> 兜底。
function boxBlockToTableHtml(lines) {
  const rows = []
  for (const line of lines) {
    const t = line.trim()
    if (!t) continue
    if (t[0] === '┌' || t[0] === '└') continue
    if (t[0] === '├') { rows.push({ sep: true }); continue }
    if (t[0] === '│' && t.endsWith('│')) {
      const inner = t.slice(1, -1)
      if (inner.includes('│')) return ''
      rows.push({ text: inner })
      continue
    }
    return ''
  }
  if (!rows.some((r) => !r.sep)) return ''

  let html = '<div class="ascii-table-diagram"><table class="ascii-table"><tbody>'
  rows.forEach((r) => {
    if (r.sep) {
      html += '<tr class="ascii-sep"><td></td></tr>'
      return
    }
    const trimmed = r.text.trim()
    if (!trimmed) return
    if (/^[━─═]+$/.test(trimmed) && trimmed.length >= 3) {
      html += '<tr class="ascii-rule"><td><i></i></td></tr>'
      return
    }
    const lead = r.text.length - r.text.trimStart().length
    const trail = r.text.length - r.text.trimEnd().length
    const center = lead >= 3 && trail >= 3 && Math.abs(lead - trail) <= 4
    html += `<tr${center ? ' class="ascii-center"' : ''}><td>${escapeHtml(trimmed)}</td></tr>`
  })
  html += '</tbody></table></div>'
  return html
}

function boxBlockToPreHtml(lines) {
  const isDiagram = lines.some((l) => /[▶◀▲▼→←↑↓]/.test(l))
  const content = isDiagram ? lines : alignBoxBlock(lines)
  return '<pre class="ascii-table"><code>' + escapeHtml(content.join('\n')) + '</code></pre>'
}

// 如果代码围栏（```）内只有框线内容，去掉围栏，避免框线表格被当成代码块转义
function stripBoxFences(lines) {
  const out = []
  let i = 0
  while (i < lines.length) {
    const t = lines[i].trim()
    if (t.startsWith('```') || t.startsWith('~~~')) {
      let k = i + 1
      while (k < lines.length) {
        const tk = lines[k].trim()
        if (tk.startsWith('```') || tk.startsWith('~~~')) break
        k++
      }
      if (k < lines.length) {
        const inner = lines.slice(i + 1, k)
        const nonEmpty = inner.filter((l) => l.trim())
        if (nonEmpty.length && nonEmpty.every((l) => isBoxLine(l))) {
          out.push(...inner)
          i = k + 1
          continue
        }
      }
    }
    out.push(lines[i])
    i++
  }
  return out
}

// 把框线块替换为占位符 ⟦ATn⟧，marked 解析后再还原为表格/图示 HTML
function extractAsciiTables(text) {
  if (!text) return { text, tables: [] }
  const lines = stripBoxFences(String(text).replace(/\r\n?/g, '\n').split('\n'))
  const out = []
  const tables = []
  let i = 0
  while (i < lines.length) {
    if (!isBoxLine(lines[i])) {
      out.push(lines[i])
      i++
      continue
    }
    let j = i
    while (j < lines.length && isBoxLine(lines[j])) j++
    const block = lines.slice(i, j)
    const html = boxBlockToTableHtml(block) || boxBlockToPreHtml(block)
    out.push('⟦AT' + tables.length + '⟧')
    tables.push(html)
    i = j
  }
  return { text: out.join('\n'), tables }
}

function applyAsciiTables(html, tables) {
  if (!tables || !tables.length) return html
  return String(html).replace(/⟦AT(\d+)⟧/g, (m, idx) => tables[parseInt(idx, 10)] || '')
}

// 管理员查看他人会话时，为正文里的站内文件链接补充归属用户参数（如 user_id=123）
function appendUrlSuffix(html, suffix) {
  if (!suffix) return html
  return String(html).replace(/\b(src|href)="(\/api\/lobster-mu\/[^"]*)"/gi, (m, attr, url) => {
    if (/([?&])user_id=/.test(url)) return m
    return `${attr}="${url}${url.includes('?') ? '&' : '?'}${suffix}"`
  })
}

function MarkdownContent({ content, streaming, urlSuffix }) {
  const html = useMemo(() => {
    try {
      const { text, tables } = extractAsciiTables(content || '')
      const { out, mathStore } = extractMath(text)
      let rawHtml = fixLiteralBold(sanitizeAnchors(marked.parse(normalizeInlineBreaks(out))))
      rawHtml = renderMathInHtml(rawHtml, mathStore)
      rawHtml = applyAsciiTables(rawHtml, tables)
      return appendUrlSuffix(rawHtml, urlSuffix)
    } catch {
      return content || ''
    }
  }, [content, urlSuffix])
  const containerRef = useRef(null)

  // 给代码块加「收起/展开」按钮：长代码块（>6行）默认收起，显示 3 行 + 渐变遮罩 + 按钮
  // 流式输出期间不折叠，避免 max-height 压缩导致内容"卡住"
  useEffect(() => {
    if (streaming) return
    const container = containerRef.current
    if (!container) return
    const pres = container.querySelectorAll('pre')
    pres.forEach((pre) => {
      const lineCount = (pre.textContent || '').split('\n').length
      if (lineCount <= 6) return
      // 跳过已处理的
      if (pre.dataset.collapsible) return
      pre.dataset.collapsible = 'true'

      // 用 relative wrapper 承载按钮和遮罩
      pre.classList.add('relative')

      const btn = document.createElement('button')
      btn.className = 'code-block-toggle'
      btn.innerHTML = '收起 ▲'
      btn.onclick = () => {
        const isCollapsed = pre.classList.toggle('code-collapsed')
        btn.textContent = isCollapsed ? `展开 ↓ (${lineCount} 行)` : '收起 ▲'
      }

      const gradient = document.createElement('div')
      gradient.className = 'code-block-gradient'

      // 收起时默认折叠
      pre.classList.add('code-collapsed')
      btn.textContent = `展开 ↓ (${lineCount} 行)`

      pre.appendChild(btn)
      pre.appendChild(gradient)
    })
  }, [html, streaming])

  return <div ref={containerRef} className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} />
}

export default MarkdownContent
