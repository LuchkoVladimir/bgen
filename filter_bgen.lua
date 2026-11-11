-- filter_bgen.lua
-- Превращает fenced div'ы bgen в FB2-теги для writer'а fb2.

-- Разворачивает верхнеуровневую <section> внутри контейнера (epigraph/annotation):
-- запоминает содержимое section, кладёт его на место родителя.
local function unwrap_top_tag(body, tag)
  local open_pat = "<" .. tag .. "[^>]*>"
  local close_pat = "</" .. tag .. ">"
  local sec_start, sec_end = body:find(open_pat)
  if not sec_start then
    return body
  end

  local depth = 1
  local pos = sec_end + 1
  local close_s
  while depth > 0 and pos <= #body do
    local open_s = body:find(open_pat, pos)
    local close_tmp = body:find(close_pat, pos)
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
  return unwrap_top_tag(body, "section")
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

-- .q и .qq: замена Span на русские кавычки.
-- .q -> «…» (внешние ёлочки)
-- .qq -> „…“ (внутренние лапки)
-- Вложенность не отслеживается: автор сам выбирает класс по уровню.
local function Span(el)
  local classes = {}
  for _, c in ipairs(el.classes) do
    classes[c] = true
  end

  -- DOCX: custom-style для кавычек
  if FORMAT == "docx" then
    if classes["q"] then
      local inner = pandoc.Span(el.content, {["custom-style"] = "Quotes"})
      return {pandoc.Str("«"), inner, pandoc.Str("»")}
    elseif classes["qq"] then
      local inner = pandoc.Span(el.content, {["custom-style"] = "Quotes"})
      return {pandoc.Str("„"), inner, pandoc.Str("“")}
    end
    return nil
  end

  if FORMAT ~= "fb2" then
    return nil
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
  local classes = {}
  for _, c in ipairs(el.classes) do
    classes[c] = true
  end

  -- DOCX: custom-style для стилей из reference.docx
  if FORMAT == "docx" then
    if classes["epigraph"] then
      el.attributes["custom-style"] = "Epigraph"
      return el
    elseif classes["text-author"] then
      el.attributes["custom-style"] = "EpigraphAuthor"
      return el
    elseif classes["annotation"] then
      el.attributes["custom-style"] = "Abstract"
      return el
    elseif classes["subtitle"] then
      el.attributes["custom-style"] = "Subtitle"
      return el
    elseif classes["asterism"] then
      local div = pandoc.Div(pandoc.Para("* * *"))
      div.attributes["custom-style"] = "Asterism"
      return div
    elseif classes["gap"] then
      local div = pandoc.Div({pandoc.Para({})})
      div.attributes["custom-style"] = "Gap"
      return div
    end
    return nil
  end

  if FORMAT ~= "fb2" then
    return nil
  end

  -- .annotation: аннотация секции
  if classes["annotation"] then
    local processed = pandoc.walk_block(el, { Div = Div })
    local inner = render_blocks(processed.content)
    return pandoc.RawBlock("fb2", "<annotation>" .. inner .. "</annotation>")
  end

  -- .frontispiece: фронтиспис (книги) --- картинка перед title в body
  if classes["frontispiece"] then
    -- Содержимое — картинка (Image). Пропускаем как есть,
    -- Pandoc сам создаст <binary> и <image>.
    -- Оборачивать в RawBlock не нужно: <image> в <body> — валидный
    -- элемент, а Pandoc сделает всё правильно.
    return nil  -- оставляем Div как есть, Pandoc разберётся
  end

  -- .epigraph: эпиграф (книги или главы)
  if classes["epigraph"] then
    local processed = pandoc.walk_block(el, { Div = Div })
    local inner = render_blocks(processed.content)
    return pandoc.RawBlock("fb2", "<epigraph>" .. inner .. "</epigraph>")
  end

  -- .text-author: автор эпиграфа
  if classes["text-author"] then
    local text = pandoc.utils.stringify(el.content)
    return pandoc.RawBlock("fb2", "<text-author>" .. text .. "</text-author>")
  end

  -- .subtitle: смысловой разделитель внутри секции
  if classes["subtitle"] then
    local processed = pandoc.walk_block(el, { Div = Div })
    local inner = render_blocks(processed.content)
    inner = unwrap_top_tag(inner, "p")
    return pandoc.RawBlock("fb2", "<subtitle>" .. inner .. "</subtitle>")
  end

  -- .asterism: сильный разделитель
  if classes["asterism"] then
    return {
      pandoc.RawBlock("fb2", "<empty-line/>"),
      pandoc.RawBlock("fb2", "<p>* * *</p>"),
      pandoc.RawBlock("fb2", "<empty-line/>"),
    }
  end

  -- .asterism: сильный разделитель
  if classes["gap"] then
    return {
      pandoc.RawBlock("fb2", "<empty-line/>"),
    }
  end

  return nil
end

return { { Div = Div, Span = Span } }

