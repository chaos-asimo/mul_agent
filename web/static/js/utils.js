/**
 * 通用工具函数
 * 与 App 类解耦，方便多个模块复用和单元测试
 */
window.Utils = (function() {
    function escapeHtml(text) {
        if (text === null || text === undefined) return '';
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(String(text)));
        return div.innerHTML;
    }

    function sanitizeThinkingContent(text) {
        if (!text) return text;
        text = String(text);
        // 过滤完整的思考块：<think>...</think>、<thinking>...</thinking> 等
        text = text.replace(/<(think|thinking|reasoning)\b[^>]*>[\s\S]*?<\/\1>/gi, '');
        // 过滤未闭合的思考标签及其之后所有内容
        text = text.replace(/<(think|thinking|reasoning)\b[^>]*>[\s\S]*/gi, '');
        return text;
    }

    function formatTimestamp(timestamp) {
        if (!timestamp) return '';
        
        let date;
        
        if (typeof timestamp === 'number') {
            if (timestamp < 1000000000000) {
                date = new Date(timestamp * 1000);
            } else {
                date = new Date(timestamp);
            }
        } else if (typeof timestamp === 'string') {
            let trimmed = timestamp.trim();
            
            if (trimmed.includes('T')) {
                const parts = trimmed.split('.');
                if (parts.length > 1) {
                    trimmed = parts[0] + '.' + parts[1].substring(0, 3);
                }
            }
            
            date = new Date(trimmed);
            
            if (isNaN(date.getTime())) {
                const normalized = trimmed.replace(' ', 'T');
                date = new Date(normalized);
            }
        } else {
            date = new Date(timestamp);
        }
        
        if (isNaN(date.getTime())) {
            return '未知时间';
        }
        
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    }

    function formatAIChatContent(content) {
        let formatted = escapeHtml(sanitizeThinkingContent(content));

        // 处理粗体强调：**文字** -> <strong>文字</strong>（[\s\S] 允许加粗内容跨行）
        formatted = formatted.replace(/\*\*([\s\S]*?)\*\*/g, '<strong>$1</strong>');

        // 处理彩色强调：[[文字]] -> <span style="color: #ef4444; font-weight: bold;">文字</span>
        formatted = formatted.replace(/\[\[(.*?)\]\]/g, '<span style="color: #ef4444; font-weight: bold;">$1</span>');

        return formatted;
    }

    /**
     * 修补 marked 漏渲染的加粗。
     * marked 的强调判定不把中文标点（如“。”）当作标点，遇到
     * “**5．业务承载与结果返回。**紧接中文” 这类“闭合 ** 紧贴非空白字符”的写法时
     * 会认为无法闭合，原样输出 **。这里把渲染结果里残留的 **文字** 补成 <strong>，
     * 同时跳过 <pre>/<code> 代码区域，避免误伤代码中的 ** 符号。
     */
    function fixLiteralBold(html) {
        if (!html) return html;
        const parts = String(html).split(/(<pre[\s\S]*?<\/pre>|<code[\s\S]*?<\/code>)/g);
        for (let i = 0; i < parts.length; i += 2) {
            parts[i] = parts[i].replace(/\*\*([^<]*?)\*\*/g, '<strong>$1</strong>');
        }
        return parts.join('');
    }

    return {
        escapeHtml,
        sanitizeThinkingContent,
        formatTimestamp,
        formatAIChatContent,
        fixLiteralBold
    };
})();
