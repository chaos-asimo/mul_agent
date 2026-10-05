// Python 语法高亮工具（移植自 v1 web/static/js/app.js 的 highlightPythonCode）
// 生成带 <span class="python-*"> 的 HTML，配合 index.css 中的 .python-* 样式使用。

export function escapeHtml(str) {
  if (str === null || str === undefined) return ''
  return String(str).replace(/[&<>"']/g, (s) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[s])
}

const keywordsControl = ['if', 'elif', 'else', 'for', 'while', 'try', 'except', 'finally', 'with', 'lambda', 'yield', 'async', 'await', 'pass', 'break', 'continue', 'return']
const keywordsDef = ['def', 'class']
const keywordsLogic = ['and', 'or', 'not', 'in', 'is']
const keywordsImport = ['import', 'from', 'as']
const keywordsOther = ['del', 'global', 'nonlocal', 'raise', 'assert']

const builtinTypes = ['list', 'dict', 'set', 'tuple', 'str', 'int', 'float', 'bool', 'type']

const builtinFuncs = ['print', 'len', 'range', 'open', 'input', 'abs', 'max', 'min', 'sum', 'sorted', 'reversed', 'enumerate', 'zip', 'map', 'filter', 'round', 'pow', 'divmod', 'chr', 'ord', 'hex', 'oct', 'bin', 'repr', 'format', 'hash', 'id', 'callable', 'isinstance', 'issubclass', 'globals', 'locals', 'dir', 'help']

const builtinConsts = ['True', 'False', 'None']

const exceptions = ['Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError', 'AttributeError', 'IOError', 'FileNotFoundError', 'RuntimeError', 'NotImplementedError', 'StopIteration', 'AssertionError', 'SyntaxError', 'ImportError', 'ModuleNotFoundError']

export function highlightPythonCode(code) {
  if (!code) return ''

  let html = escapeHtml(code)

  // 占位符策略：先把字符串/注释换成占位符，避免后续关键字替换破坏它们
  const placeholders = []
  let placeholderIndex = 0

  // 三引号字符串（支持 f/r/b/u 前缀）
  html = html.replace(/((?:[frbuFRBU])?("""[\s\S]*?""")|(?:[frbuFRBU])?('''[\s\S]*?'''))/g, (match) => {
    const placeholder = `__PY_STRING_${placeholderIndex}__`
    placeholders.push({ index: placeholderIndex, type: 'string', content: match })
    placeholderIndex++
    return placeholder
  })

  // 单/双引号字符串
  html = html.replace(/((?:[frbuFRBU])?("[^"]*")|(?:[frbuFRBU])?('[^']*'))/g, (match) => {
    const placeholder = `__PY_STRING_${placeholderIndex}__`
    placeholders.push({ index: placeholderIndex, type: 'string', content: match })
    placeholderIndex++
    return placeholder
  })

  // 单行注释
  html = html.replace(/(#.*$)/gm, (match) => {
    const placeholder = `__PY_COMMENT_${placeholderIndex}__`
    placeholders.push({ index: placeholderIndex, type: 'comment', content: match })
    placeholderIndex++
    return placeholder
  })

  // 数字
  html = html.replace(/\b(\d+\.?\d*)\b/g, '<span class="python-number">$1</span>')
  // 装饰器
  html = html.replace(/(@\w+)/g, '<span class="python-decorator">$1</span>')
  // 类定义
  html = html.replace(/\b(class)\s+(\w+)/g, '<span class="python-keyword-def">$1</span> <span class="python-class">$2</span>')
  // 函数定义
  html = html.replace(/\b(def)\s+(\w+)/g, '<span class="python-keyword-def">$1</span> <span class="python-function">$2</span>')
  // 魔法方法
  html = html.replace(/\b(__\w+__)\b/g, '<span class="python-magic">$1</span>')

  const wrapWords = (arr, cls) => {
    arr.forEach((kw) => {
      html = html.replace(new RegExp(`\\b(${kw})\\b`, 'g'), `<span class="${cls}">$1</span>`)
    })
  }
  wrapWords(exceptions, 'python-exception')
  wrapWords(builtinConsts, 'python-builtin-const')
  wrapWords(builtinTypes, 'python-builtin-type')
  wrapWords(builtinFuncs, 'python-builtin-func')
  wrapWords(keywordsControl, 'python-keyword-control')
  wrapWords(keywordsLogic, 'python-keyword-logic')
  wrapWords(keywordsImport, 'python-keyword-import')
  wrapWords(keywordsOther, 'python-keyword-control')

  // 还原占位符
  placeholders.forEach((ph) => {
    const tag = ph.type === 'comment' ? 'python-comment' : 'python-string'
    const placeholder = ph.type === 'comment' ? `__PY_COMMENT_${ph.index}__` : `__PY_STRING_${ph.index}__`
    html = html.replace(placeholder, `<span class="${tag}">${ph.content}</span>`)
  })

  return html
}
