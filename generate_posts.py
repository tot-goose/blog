import xml.etree.ElementTree as ET
import urllib.request
import os
import re
import requests
from datetime import datetime
from email.utils import parsedate_to_datetime

RSS_URL = os.environ.get("RSS_URL")
POSTS_DIR = "_posts"
IMAGES_DIR = "assets/images/posts"
MAX_ITEMS = 200
PROCESSED_FILE = ".rss_processed.txt"

# 🌐 Заголовки, чтобы сервер не блокировал запрос
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive'
}

# 🔄 Словарь транслитерации
TRANS_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '',
    'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    ' ': '-', '_': '-', '/': '-', '\\': '-', '—': '-', '–': '-',
    '.': '', ',': '', '(': '', ')': '', '!': '', '?': '', '"': '', "'": '',
}

def slugify(text):
    if not text: return 'post'
    text = text.lower()
    result = ''
    for char in text:
        result += TRANS_MAP.get(char, char)
    result = re.sub(r'[^\w\s-]', '', result)
    result = re.sub(r'[-\s]+', '-', result).strip('-_')
    return result or 'post'

def load_processed():
    """Загружает список уже обработанных ссылок"""
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed(processed):
    """Сохраняет список обработанных ссылок"""
    with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(processed)))

def download_image(url, slug):
    if not url: return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        
        ext = 'jpg'
        ct = resp.headers.get('content-type', '')
        if 'png' in ct: ext = 'png'
        elif 'webp' in ct: ext = 'webp'
        
        filename = f"{slug}.{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)
        os.makedirs(IMAGES_DIR, exist_ok=True)
        
        with open(filepath, 'wb') as f:
            f.write(resp.content)
        
        return f"/{filepath}"
    except Exception as e:
        print(f"   ⚠️ Ошибка картинки: {e}")
        return None

def clean_html(html):
    """Убирает лишние теги из Turbo контента"""
    if not html: return ""
    html = re.sub(r'<header>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<figure>.*?</figure>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', html)
    return re.sub(r'\n\s*\n', '\n\n', text).strip()

def main():
    if not RSS_URL:
        print("❌ RSS_URL не задан")
        exit(1)

    print(f"📡 Загрузка: {RSS_URL}")
    
    try:
        req = urllib.request.Request(RSS_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as response:
            xml_data = response.read()
        print("✅ RSS успешно загружен")
    except Exception as e:
        print(f"❌ Ошибка скачивания: {e}")
        exit(1)
    
    print("🔍 Парсинг XML...")
    
    try:
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"❌ Ошибка парсинга XML: {e}")
        exit(1)
    
    items = root.findall('.//item')
    print(f"📊 Найдено <item> элементов: {len(items)}")
    
    if len(items) == 0:
        print("⚠️ Элементы <item> не найдены!")
        return
    
    # Загружаем историю обработанных ссылок
    processed = load_processed()
    print(f"📁 Уже обработано ссылок: {len(processed)}")
    
    os.makedirs(POSTS_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    
    new_count = 0
    
    for i, item in enumerate(items, 1):
        if new_count >= MAX_ITEMS:
            print(f"⏹️ Лимит {MAX_ITEMS} достигнут")
            break
        
        title_elem = item.find('title')
        link_elem = item.find('link')
        pubdate_elem = item.find('pubDate')
        enclosure_elem = item.find('enclosure')
        turbo_elem = item.find('{http://turbo.yandex.ru}content')
        
        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
        link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
        
        if not title or not link:
            continue
        
        # Пропускаем уже обработанные ссылки
        if link in processed:
            print(f"   ⏭️ [{i}] Уже обработано: {title[:40]}...")
            continue
        
        print(f"\n🔍 [{i}/{len(items)}] {title[:50]}...")
        
        # Проверяем наличие картинки
        img_url = None
        if enclosure_elem is not None:
            img_url = enclosure_elem.get('url')
            img_type = enclosure_elem.get('type', '')
            if 'image' not in img_type:
                img_url = None
        
        if not img_url:
            print(f"   ⏭️ Пропуск: нет картинки")
            continue
        
        print(f"   🖼️ Картинка найдена")
        
        # Дата
        pubdate_text = pubdate_elem.text if pubdate_elem is not None else None
        try:
            dt = parsedate_to_datetime(pubdate_text) if pubdate_text else datetime.now()
        except:
            dt = datetime.now()
        
        date_str = dt.strftime("%Y-%m-%d")
        iso_date = dt.strftime("%Y-%m-%d %H:%M:%S +0000")
        slug = slugify(title)
        
        # Скачиваем картинку
        image_path = download_image(img_url, slug)
        
        # Извлекаем контент
        content_text = ""
        if turbo_elem is not None and turbo_elem.text:
            content_text = clean_html(turbo_elem.text)
        
        if len(content_text) < 50:
            content_text = "Описание недоступно."
        
        # Создаем файл
        filename = f"{date_str}-{slug}.md"
        filepath = os.path.join(POSTS_DIR, filename)
        
        if os.path.exists(filepath):
            filename = f"{date_str}-{slug}-{dt.strftime('%H%M')}.md"
            filepath = os.path.join(POSTS_DIR, filename)
        
        frontmatter = (
            f"---\n"
            f"title: \"{title}\"\n"
            f"date: {iso_date}\n"
            f"source: \"{link}\"\n"
            f"layout: post\n"
            f"image: \"{image_path}\"\n"
            f"---\n\n"
        )
        
        content = f"{frontmatter}{content_text}\n\n[Читать оригинал]({link})"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Добавляем ссылку в обработанные и сохраняем файл истории
        processed.add(link)
        save_processed(processed)
        
        new_count += 1
        print(f"   ✅ Создан: {filename}")
    
    print(f"\n{'='*40}")
    print(f"🏁 Готово! Создано постов: {new_count}")
    print(f"📁 Всего в истории: {len(processed)}")
    print(f"{'='*40}")

if __name__ == "__main__":
    main()
