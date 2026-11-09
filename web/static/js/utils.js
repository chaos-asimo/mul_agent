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

        // 处理粗体强调：**文字** -> <strong>文字</strong>
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // 处理彩色强调：[[文字]] -> <span style="color: #ef4444; font-weight: bold;">文字</span>
        formatted = formatted.replace(/\[\[(.*?)\]\]/g, '<span style="color: #ef4444; font-weight: bold;">$1</span>');

        return formatted;
    }

    return {
        escapeHtml,
        sanitizeThinkingContent,
        formatTimestamp,
        formatAIChatContent
    };
})();
