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

    // ---- ASCII 框线表格处理 ----
    // 模型输出的框线表格在浏览器里很难保证对齐：中文/全角字符宽度、框线字符宽度、
    // 字体回退都会破坏「字符个数 = 显示列数」的假设。
    // 因此单列框线块直接转成 HTML 表格（用 CSS 边框绘制框线），彻底摆脱字体宽度问题；
    // 多列/复杂图示则退回 <pre> 并按显示宽度补齐（尽力而为）。
    function displayWidth(text) {
        let w = 0;
        for (const ch of String(text || '')) {
            const code = ch.codePointAt(0);
            if ((code >= 0x0300 && code <= 0x036F) || code === 0x200B) continue; // 组合/零宽字符
            const wide =
                (code >= 0x1100 && code <= 0x115F) ||
                code === 0x2329 || code === 0x232A ||
                (code >= 0x2E80 && code <= 0xA4CF) ||
                (code >= 0xAC00 && code <= 0xD7A3) ||
                (code >= 0xF900 && code <= 0xFAFF) ||
                (code >= 0xFE10 && code <= 0xFE19) ||
                (code >= 0xFE30 && code <= 0xFE6F) ||
                (code >= 0xFF00 && code <= 0xFF60) ||
                (code >= 0xFFE0 && code <= 0xFFE6) ||
                (code >= 0x1F300 && code <= 0x1F64F) ||
                (code >= 0x1F900 && code <= 0x1F9FF) ||
                (code >= 0x20000 && code <= 0x3FFFD);
            w += wide ? 2 : 1;
        }
        return w;
    }

    function isBoxLine(line) {
        return /[│┌┐└┘├┤┬┴┼]/.test(line);
    }

    function padDisplayRight(text, width) {
        const diff = width - displayWidth(text);
        return diff > 0 ? text + ' '.repeat(diff) : text;
    }

    // 对齐一个连续的框线块，返回新的行数组
    function alignBoxBlock(lines) {
        const cells = [];
        let colCount = 0;
        lines.forEach((line) => {
            const t = line.trim();
            if (/^│.*│$/.test(t)) {
                const parts = t.slice(1, -1).split('│').map((p) => p.replace(/\s+$/, ''));
                colCount = Math.max(colCount, parts.length);
                cells.push(parts);
            } else {
                cells.push(null);
            }
        });
        if (colCount === 0) return lines;

        const widths = new Array(colCount).fill(0);
        cells.forEach((parts) => {
            if (!parts) return;
            for (let c = 0; c < parts.length; c++) {
                widths[c] = Math.max(widths[c], displayWidth(parts[c]));
            }
        });

        const junction = { '┌': '┬', '├': '┼', '└': '┴' };
        return lines.map((line, idx) => {
            const t = line.trim();
            const parts = cells[idx];
            if (parts) {
                const padded = [];
                for (let c = 0; c < colCount; c++) {
                    padded.push(padDisplayRight(parts[c] || '', widths[c]));
                }
                return '│' + padded.join('│') + '│';
            }
            const border = t.match(/([┌├└])([─┬┴┼]+)([┐┤┘])/);
            if (border && border[1] && border[3] && junction[border[1]]) {
                const mid = junction[border[1]];
                return border[1] + widths.map((w) => '─'.repeat(w)).join(mid) + border[3];
            }
            return line;
        });
    }

    // 单列框线块 -> HTML 表格；无法识别（多列/复杂图示）时返回空字符串
    function boxBlockToTableHtml(lines) {
        const rows = [];
        for (const line of lines) {
            const t = line.trim();
            if (!t) continue;
            if (t[0] === '┌' || t[0] === '└') continue; // 上下外框由 CSS 边框代替
            if (t[0] === '├') { rows.push({ sep: true }); continue; }
            if (t[0] === '│' && t.endsWith('│')) {
                const inner = t.slice(1, -1);
                if (inner.includes('│')) return ''; // 多列，退回 pre
                rows.push({ text: inner });
                continue;
            }
            return ''; // 含箭头等复杂内容，退回 pre
        }
        if (!rows.some((r) => !r.sep)) return '';

        let html = '<div class="ascii-table-diagram"><table class="ascii-table"><tbody>';
        rows.forEach((r) => {
            if (r.sep) {
                html += '<tr class="ascii-sep"><td></td></tr>';
                return;
            }
            const trimmed = r.text.trim();
            if (!trimmed) return;
            if (/^[━─═]+$/.test(trimmed) && trimmed.length >= 3) {
                html += '<tr class="ascii-rule"><td><i></i></td></tr>';
                return;
            }
            const lead = r.text.length - r.text.trimStart().length;
            const trail = r.text.length - r.text.trimEnd().length;
            // 左右留白较多且大致对称，视为居中标题
            const center = lead >= 3 && trail >= 3 && Math.abs(lead - trail) <= 4;
            html += `<tr${center ? ' class="ascii-center"' : ''}><td>${escapeHtml(trimmed)}</td></tr>`;
        });
        html += '</tbody></table></div>';
        return html;
    }

    // 多列/复杂图示的兜底：优先原样保留（箭头类图示不重排），否则按显示宽度对齐
    function boxBlockToPreHtml(lines) {
        const isDiagram = lines.some((l) => /[▶◀▲▼→←↑↓]/.test(l));
        const content = isDiagram ? lines : alignBoxBlock(lines);
        return '<pre class="ascii-table">' + escapeHtml(content.join('\n')) + '</pre>';
    }

    // 如果代码围栏（```）内只有框线内容，去掉围栏，避免框线表格被当成代码块转义
    function stripBoxFences(lines) {
        const out = [];
        let i = 0;
        while (i < lines.length) {
            const t = lines[i].trim();
            if (t.startsWith('```') || t.startsWith('~~~')) {
                let k = i + 1;
                while (k < lines.length) {
                    const tk = lines[k].trim();
                    if (tk.startsWith('```') || tk.startsWith('~~~')) break;
                    k++;
                }
                if (k < lines.length) {
                    const inner = lines.slice(i + 1, k);
                    const nonEmpty = inner.filter((l) => l.trim());
                    if (nonEmpty.length && nonEmpty.every((l) => isBoxLine(l))) {
                        out.push(...inner);
                        i = k + 1;
                        continue;
                    }
                }
            }
            out.push(lines[i]);
            i++;
        }
        return out;
    }

    /**
     * 把文本中的框线块替换为占位符 ⟦ATn⟧，返回占位符文本与 HTML 列表。
     * 用于 Markdown 渲染（marked.parse 之后再用 applyAsciiTables 还原），
     * 这样无论是 HTML 表格还是 <pre> 兜底，都不会被 marked 当作文本转义。
     */
    function extractAsciiTables(text) {
        if (!text) return { text: text, tables: [] };
        const lines = stripBoxFences(String(text).replace(/\r\n?/g, '\n').split('\n'));
        const out = [];
        const tables = [];
        let i = 0;
        while (i < lines.length) {
            if (!isBoxLine(lines[i])) {
                out.push(lines[i]);
                i++;
                continue;
            }
            let j = i;
            while (j < lines.length && isBoxLine(lines[j])) j++;
            const block = lines.slice(i, j);
            const html = boxBlockToTableHtml(block) || boxBlockToPreHtml(block);
            out.push('⟦AT' + tables.length + '⟧');
            tables.push(html);
            i = j;
        }
        return { text: out.join('\n'), tables: tables };
    }

    function applyAsciiTables(html, tables) {
        if (!tables || !tables.length) return html;
        return String(html).replace(/⟦AT(\d+)⟧/g, (match, idx) => tables[parseInt(idx, 10)] || '');
    }

    function formatAIChatContent(content) {
        const cleaned = sanitizeThinkingContent(content);
        if (!cleaned) return '';
        const emphasize = (escaped) => escaped
            // 处理粗体强调：**文字** -> <strong>文字</strong>
            .replace(/\*\*([\s\S]*?)\*\*/g, '<strong>$1</strong>')
            // 处理彩色强调：[[文字]] -> 红色加粗
            .replace(/\[\[(.*?)\]\]/g, '<span style="color: #ef4444; font-weight: bold;">$1</span>');

        const lines = String(cleaned).replace(/\r\n?/g, '\n').split('\n');
        const out = [];
        let i = 0;
        while (i < lines.length) {
            if (!isBoxLine(lines[i])) {
                out.push(emphasize(escapeHtml(lines[i])));
                i++;
                continue;
            }
            let j = i;
            while (j < lines.length && isBoxLine(lines[j])) j++;
            const block = lines.slice(i, j);
            out.push(boxBlockToTableHtml(block) || boxBlockToPreHtml(block));
            i = j;
        }
        return out.join('\n');
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
        fixLiteralBold,
        displayWidth,
        alignBoxBlock,
        extractAsciiTables,
        applyAsciiTables
    };
})();
