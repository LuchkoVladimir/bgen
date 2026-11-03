-- filter_bgen.lua
-- Превращает fenced div'ы bgen в FB2-теги для writer'а fb2.

-- Разворачивает верхнеуровневую <section> внутри контейнера (epigraph/annotation):
-- запоминает содержимое section, кладёт его на место родителя.
local function unwrap_top_section(body)
  local sec_start, sec_end = body:find("<section[^>]*>")
  if not sec_start then
    return body
  end

  local depth = 1
  local pos = sec_end + 1
  local close_s
  while depth > 0 and pos <= #body do
    local open_s = body:find("<section[^>]*>", pos)
    local close_tmp = body:find("</section>", pos)
    if not close_tmp then break end
    if open_s and open_s < close_tmp then
      depth = depth + 1
      pos = open_s + 1
    else
      depth = depth - 1
      if depth == 0 then
        close_s = close_tmp
        break
      end
      pos = close_tmp + 1
    end
  end

  if not close_s then
    return body
  end

  return body:sub(sec_end + 1, close_s - 1)
end

-- Сериализует один блок в FB2-строку и разворачивает верхнеуровневую секцию.
local function render_one_block(block)
  local doc = pandoc.Pandoc({ block }, {})
  local fb2_text = pandoc.write(doc, "fb2")
  local body = fb2_text:match("<body>(.-)</body>") or fb2_text
  return unwrap_top_section(body)
end

-- Сериализует список блоков, обрабатывая каждый отдельно.
local function render_blocks(blocks)
  local parts = {}
  for _, block in ipairs(blocks) do
    local rendered = render_one_block(block)
    if rendered ~= "" then
      table.insert(parts, rendered)
    end
  end
  return table.concat(parts, "\n")
end

-- Сериализует .poem в <poem><stanza><v>...
-- Каждый Para/Plain внутри .poem — строфа; SoftBreak/LineBreak — границы строк.
-- LineBlock (если автор использовал | в Markdown) — тоже строфа.
local function render_poem(el)
  local poem_parts = {}
  local stanza_lines = {}

  local function flush_stanza()
    if #stanza_lines == 0 then return end
    local stanza_xml = {}
    for _, l in ipairs(stanza_lines) do
      table.insert(stanza_xml, "<v>" .. l .. "</v>")
    end
    table.insert(poem_parts, "<stanza>" .. table.concat(stanza_xml) .. "</stanza>")
    stanza_lines = {}
  end

  for _, block in ipairs(el.content) do
    if block.t == "Para" or block.t == "Plain" then
      local line = {}
      for _, inline in ipairs(block.content) do
        if inline.t == "SoftBreak" or inline.t == "LineBreak" then
          if #line > 0 then
            table.insert(stanza_lines, pandoc.utils.stringify(line))
            line = {}
          end
        else
          table.insert(line, inline)
        end
      end
      if #line > 0 then
        table.insert(stanza_lines, pandoc.utils.stringify(line))
      end
      flush_stanza()
    elseif block.t == "LineBlock" then
      for _, line_inlines in ipairs(block.content) do
        table.insert(stanza_lines, pandoc.utils.stringify(line_inlines))
      end
      flush_stanza()
    end
    -- Прочие блоки (RawBlock от вложенных Div и т.п.) пропускаем:
    -- они уже обработаны walk_block и не являются строками стиха.
  end
  flush_stanza()

  return pandoc.RawBlock("fb2", "<poem>" .. table.concat(poem_parts) .. "</poem>")
end

-- .q и .qq: замена Span на русские кавычки.
-- .q -> «…» (внешние ёлочки)
-- .qq -> „…“ (внутренние лапки)
-- Вложенность не отслеживается: автор сам выбирает класс по уровню.
local function Span(el)
  if FORMAT ~= "fb2" then
    return nil
  end

  local classes = {}
  for _, c in ipairs(el.classes) do
    classes[c] = true
  end

  local open_q, close_q
  if classes["q"] then
    open_q, close_q = "«", "»"
  elseif classes["qq"] then
    open_q, close_q = "„", "“"
  else
    return nil
  end

  local result = { pandoc.Str(open_q) }
  for _, inline in ipairs(el.content) do
    table.insert(result, inline)
  end
  table.insert(result, pandoc.Str(close_q))
  return result
end

local function Div(el)
  if FORMAT ~= "fb2" then
    return nil
  end

  local classes = {}
  for _, c in ipairs(el.classes) do
    classes[c] = true
  end

  -- .annotation: аннотация секции
  if classes["annotation"] then
    local processed = pandoc.walk_block(el, { Div = Div })
    local inner = render_blocks(processed.content)
    return pandoc.RawBlock("fb2", "<annotation>" .. inner .. "</annotation>")
  end

  -- .epigraph: эпиграф (книги или главы)
  if classes["epigraph"] then
    local processed = pandoc.walk_block(el, { Div = Div })
    local inner = render_blocks(processed.content)
    return pandoc.RawBlock("fb2", "<epigraph>" .. inner .. "</epigraph>")
  end

  -- .asterism: сильный разделитель
  if classes["asterism"] then
    return pandoc.RawBlock("fb2", "<p>* * *</p>")
  end

  -- .text-author: автор эпиграфа
  if classes["text-author"] then
    local text = pandoc.utils.stringify(el.content)
    return pandoc.RawBlock("fb2", "<text-author>" .. text .. "</text-author>")
  end

  -- .poem: стихотворение
  if classes["poem"] then
    return render_poem(el)
  end

  return nil
end

return { { Div = Div, Span = Span } }

