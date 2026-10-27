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

function MarkdownContent({ content, streaming }) {
  const html = useMemo(() => {
    try {
      const raw = content || ''
      const { out, mathStore } = extractMath(raw)
      const rawHtml = sanitizeAnchors(marked.parse(normalizeInlineBreaks(out)))
      return renderMathInHtml(rawHtml, mathStore)
    } catch {
      return content || ''
    }
  }, [content])
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
