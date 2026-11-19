-- filter_bgen.lua
-- Превращает fenced div'ы bgen в FB2-теги для writer'а fb2.
-- Также обрабатывает Span (типографика: [min]{.t}, [текст]{.q} и т.д.)

-- Copyright (C) 2026 Владимир Лучко
-- This program is free software: you can redistribute it and/or modify it under the terms
-- of the GNU General Public License as published by the Free Software Foundation, either
-- version 3 of the License, or (at your option) any later version.
-- This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
-- without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
-- See the GNU General Public License for more details.
-- You should have received a copy of the GNU General Public License along with this program.
-- If not, see https://www.gnu.org/licenses/.

-- ============================================================
-- Типографика: читает typography.txt (separator=:)
-- ============================================================

local _typography = nil

local function load_typography()
  local path = os.getenv("BGEN_TYPOGRAPHY")
  if not path or path == "" then
    local script_dir = debug.getinfo(1, "S").source:match("@(.*[/\\])")
    path = (script_dir or "") .. "schemas/typography.txt"
  end

  local f = io.open(path, "r")
  if not f then
    io.stderr:write("filter_bgen.lua: не найден " .. path .. "\n")
    return {}
  end

  local sep = nil
  local entries = {}


  for line in f:lines() do
    if line:match("^%s*#") or line:match("^%s*$") then
      goto continue
    end
    local s = line:match("^separator=(.)%s*$")
    if s then
      sep = s
      goto continue
    end
    if not sep then
      goto continue
    end

    local parts = {}
    for part in (line .. sep):gmatch("(.-)" .. sep) do
      table.insert(parts, part)
    end

    if #parts == 2 then
      local key, value = parts[1], parts[2]
      if key and value and key ~= "" then
        entries[key] = { kind = "single", value = value }
      end
    elseif #parts == 3 then
      local key, open_q, close_q = parts[1], parts[2], parts[3]
      if key and open_q and close_q and key ~= "" then
        entries[key] = { kind = "pair", open_q = open_q, close_q = close_q }
      end
    end

    ::continue::
  end
  f:close()
  return entries
end

local function get_typography()
  if _typography == nil then
    _typography = load_typography()
  end
  return _typography
end

-- Span: типографика.
-- .t — одиночная замена: [min]{.t} → − (текст = ключ в typography.txt).
-- .q/.qq/.qqq — парная замена: [текст]{.q} → «текст».
local function Span(el)
  local entries = get_typography()
  if not entries then return nil end

  local classes = {}
  for _, c in ipairs(el.classes) do
    classes[c] = true
  end

  -- .t: одиночная замена (текст = ключ)
  if classes["t"] then
    local text = pandoc.utils.stringify(el.content)
    local entry = entries[text]
    if entry and entry.kind == "single" then
      return pandoc.Str(entry.value)
    end
    return nil
  end

  -- Парные: [текст]{.key} → open + content + close
  for key, entry in pairs(entries) do
    if classes[key] and entry.kind == "pair" then
      local result = { pandoc.Str(entry.open_q) }
      for _, inline in ipairs(el.content) do
        table.insert(result, inline)
      end
      table.insert(result, pandoc.Str(entry.close_q))
      return result
    end
  end
  return nil
end


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

local function Div(el)
  local classes = {}
  for _, c in ipairs(el.classes) do
    classes[c] = true
  end

  -- EPUB: asterism
  if FORMAT:match("epub") then
    if classes["asterism"] then
      local div = pandoc.Div(pandoc.Para("* * *"))
      div.attributes["class"] = "asterism"
      return div
    end
    return nil
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

  -- TXT: asterism и gap
  if FORMAT == "plain" then
    if classes["asterism"] then
      return pandoc.Para(pandoc.Str("* * *"))
    elseif classes["gap"] then
      return pandoc.Para(pandoc.Str("- -"))
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

-- LineBlock (стихи через |): для DOCX оборачиваем в Div с custom-style="Poem",
-- чтобы Pandoc применил стиль Poem из reference.docx.
-- Для FB2 не трогаем (Pandoc сам делает <poem><stanza><v>).
local function LineBlock(el)
  if FORMAT:match("epub") then
    local div = pandoc.Div({el})
    div.attributes["class"] = "poem"
    return div
  end

  if FORMAT == "docx" then
    local div = pandoc.Div({el})
    div.attributes["custom-style"] = "Poem"
    return div
  end
  return nil
end

return { { Div = Div, Span = Span, LineBlock = LineBlock } }

