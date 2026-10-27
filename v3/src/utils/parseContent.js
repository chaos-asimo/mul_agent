// 将助手消息内容解析为分段：文本 / 工具调用 / 工具结果
// 用于 WorkBuddy 风格的可视化渲染（工具卡片而非纯文本）

const TOOL_ICONS = {
  '创建脚本': '📝',
  '执行脚本': '⚙️',
  '网页搜索': '🔍',
  '搜索': '🔍',
  'MCP': '🔌',
  '技能': '🧩',
  '脚本': '📝',
  '工具': '🔧',
}

// 匹配工具调用起始行：🔧 正在执行工具: xxx...  或  🔧 正在调用 MCP 工具: xxx...
// 或  🔧 正在执行技能: xxx...
const TOOL_CALL_RE = /^(🔧|⚙️)\s*(?:正在执行工具|正在调用\s*MCP\s*工具|正在执行技能|检测到需要编写脚本)[：:]\s*(.+?)\s*\.{0,3}\s*$/
// 匹配工具结果起始行：📋 工具执行结果:  或  📋 脚本执行结果:  或  📋 MCP 工具 xxx 调用成功...
const TOOL_RESULT_RE = /^(📋)\s*(?:工具执行结果|脚本执行结果|执行结果|搜索到\s*\d+\s*条结果|MCP\s*工具\s*\S+\s*调用成功|技能\s*\S+\s*执行完成)[：:]*\s*(.*)$/
// 分隔线：后端拼接工具结果时固定以 "\n\n---\n\n" 收尾，其后必为助手正文，
// 故裸 --- 视为结果段结束边界（代码围栏内的 --- 不生效，见下方 inFence 判断）
const SEP_RE = /^-{3,}\s*$/
// 代码围栏
const FENCE_RE = /^\s*```/

export function parseAssistantContent(content) {
  if (!content) return [{ type: 'text', content: '' }]
  const lines = content.split('\n')
  const segments = []
  let buf = []
  let i = 0

  const flushText = () => {
    const text = buf.join('\n').trim()
    if (text) segments.push({ type: 'text', content: text })
    buf = []
  }

  while (i < lines.length) {
    const line = lines[i]

    // 工具调用行
    const callMatch = line.match(TOOL_CALL_RE)
    if (callMatch) {
      flushText()
      const rawName = callMatch[2].trim()
      // 提取工具类型用于图标
      let toolType = '工具'
      if (rawName.includes('脚本') || rawName.includes('编写')) toolType = '创建脚本'
      else if (rawName.includes('搜索')) toolType = '搜索'
      else if (rawName.includes('MCP')) toolType = 'MCP'
      else if (rawName.includes('技能')) toolType = '技能'
      segments.push({
        type: 'tool_call',
        name: rawName,
        icon: TOOL_ICONS[toolType] || '🔧',
      })
      i++
      continue
    }

    // 工具结果行
    const resultMatch = line.match(TOOL_RESULT_RE)
    if (resultMatch) {
      flushText()
      // 收集结果内容，直到遇到下一个工具标记或结果段边界分隔线；代码围栏内的内容不截断
      const resultLines = []
      if (resultMatch[2]) resultLines.push(resultMatch[2])
      i++
      let inFence = false
      while (i < lines.length) {
        const next = lines[i]
        if (next.match(FENCE_RE)) {
          inFence = !inFence
          resultLines.push(next)
          i++
          continue
        }
        if (!inFence) {
          if (next.match(TOOL_CALL_RE) || next.match(TOOL_RESULT_RE)) break
          if (next.match(SEP_RE)) break
        }
        resultLines.push(next)
        i++
      }
      segments.push({
        type: 'tool_result',
        content: resultLines.join('\n').trim(),
      })
      continue
    }

    // 分隔线 → 忽略（顶层分隔线本身不作为内容）
    if (line.match(SEP_RE)) {
      flushText()
      i++
      continue
    }

    buf.push(line)
    i++
  }
  flushText()

  // 如果没有解析出任何工具片段，返回纯文本
  if (segments.every((s) => s.type === 'text')) {
    return [{ type: 'text', content }]
  }
  return segments
}
