-- filter_bgen.lua
-- Превращает fenced div'ы bgen в FB2-теги для writer'а fb2.
-- Для остальных форматов поведение можно будет добавить позже.

local function render_blocks(blocks)
  -- Рекурсивно сериализуем Blocks в строку XML.
  -- Нам нужны только те элементы, которые уже стали RawBlock или простыми блоками.
  local parts = {}
  for _, block in ipairs(blocks) do
    if block.t == "RawBlock" then
      table.insert(parts, block.text)
    elseif block.t == "Para" or block.t == "Plain" then
      -- Простой параграф: оборачиваем в <p>
      local text = pandoc.utils.stringify(block)
      table.insert(parts, "<p>" .. text .. "</p>")
    elseif block.t == "BlockQuote" then
      -- Цитата внутри эпиграфа: <cite>
      local cite_parts = {}
      for _, inner in ipairs(block.content) do
        if inner.t == "Para" or inner.t == "Plain" then
          table.insert(cite_parts, "<p>" .. pandoc.utils.stringify(inner) .. "</p>")
        end
      end
      table.insert(parts, "<cite>" .. table.concat(cite_parts) .. "</cite>")
    else
      -- Остальное (списки, заголовки и т.п.) внутри эпиграфа не поддерживаем
      -- и просто пропускаем, чтобы не сломать XML.
    end
  end
  return table.concat(parts)
end

local function Div(el)
  if FORMAT ~= "fb2" then
    return nil
  end

  local classes = {}
  for _, c in ipairs(el.classes) do
    classes[c] = true
  end

  -- .text-author: автор эпиграфа
  if classes["text-author"] then
    local text = pandoc.utils.stringify(el.content)
    return pandoc.RawBlock("fb2", "<text-author>" .. text .. "</text-author>")
  end

  -- .epigraph: эпиграф (книги или главы)
  if classes["epigraph"] then
    -- Сначала обрабатываем вложенные div'ы (например, .text-author)
    local processed = pandoc.walk_block(el, { Div = Div })
    local inner = render_blocks(processed.content)
    return pandoc.RawBlock("fb2", "<epigraph>" .. inner .. "</epigraph>")
  end

  -- .poem: стихотворение
  if classes["poem"] then
    local poem_parts = {}
    -- Содержимое .poem: строки разделены пустыми строками на строфы
    local raw = pandoc.utils.stringify(el.content)
    -- Простейший разбор: строки как <v>, пустые строки разделяют строфы
    local stanza = {}
    for line in raw:gmatch("[^\n]+") do
      line = line:match("^%s*(.-)%s*$")
      if line ~= "" then
        table.insert(stanza, "<v>" .. line .. "</v>")
      else
        if #stanza > 0 then
          table.insert(poem_parts, "<stanza>" .. table.concat(stanza) .. "</stanza>")
          stanza = {}
        end
      end
    end
    if #stanza > 0 then
      table.insert(poem_parts, "<stanza>" .. table.concat(stanza) .. "</stanza>")
    end
    return pandoc.RawBlock("fb2", "<poem>" .. table.concat(poem_parts) .. "</poem>")
  end

  -- .asterism: сильный разделитель
  if classes["asterism"] then
    return pandoc.RawBlock("fb2", "<p>* * *</p>")
  end

  return nil
end

return { { Div = Div } }

