#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ozon Position Monitor — лог: номер скролла вместо страницы
"""

import time
import re
import csv
import os
import random
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, Set
from seleniumbase import SB

SEARCH_QUERY = "Плакат"
TARGET_SKU = "4223710811"
CHECK_INTERVAL = 1200 # интервал проверки 20 минут

MAX_SCROLLS = 20 # количество скроллов
SCROLL_SIZE = 1000
SCROLL_PAUSE = 2.0

LOG_FILE = "ozon_position_log.csv"


@dataclass
class CheckResult:
    timestamp: str
    query: str
    sku: str
    found: bool
    position: int  # абсолютная позиция (1, 2, 3...)
    scroll_num: int  # ← номер скролла, на котором найден
    pos_on_scroll: int  # позиция внутри текущего скролла
    total_scrolled: int  # сколько всего товаров проверено
    error: Optional[str] = None


class OzonMonitor:
    def __init__(self):
        pass

    def _delay(self, a: float, b: float):
        time.sleep(random.uniform(a, b))

    def _scroll(self, sb, pixels: int):
        sb.execute_script(f"window.scrollBy(0, {pixels})")

    def _extract_skus(self, html: str) -> list:
        skus = re.findall(r'href="/product/[^"]*-(\d{9,10})/\?[^"]*"', html)
        if not skus:
            skus = re.findall(r'data-sku="(\d+)"', html)
        if not skus:
            skus = re.findall(r'"sku":\s*"(\d+)"', html)
        return skus

    def check(self) -> CheckResult:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            with SB(uc=True, headless=False) as sb:
                print(f"\n[{self._time()}] === ПРОВЕРКА ===")
                print(f"  Запрос: '{SEARCH_QUERY}'")
                print(f"  SKU: {TARGET_SKU}")

                # Заходим на Ozon
                print(f"[{self._time()}] Загрузка ozon.ru...")
                sb.open("https://www.ozon.ru")
                self._delay(4, 7)
                self._scroll(sb, 500)
                self._delay(2, 3)

                # Поисковая строка
                print(f"[{self._time()}] Поиск строки...")
                search_input = None
                selectors = [
                    'input[name="text"]',
                    'input[placeholder*="Искать" i]',
                    'input[type="text"]',
                    'input[class*="search"]',
                ]
                for sel in selectors:
                    if sb.is_element_visible(sel):
                        search_input = sel
                        print(f"  ✅ Найдено: {sel}")
                        break

                if not search_input:
                    return CheckResult(ts, SEARCH_QUERY, TARGET_SKU, False, 0, 0, 0, 0, "Поиск не найден")

                # Ввод запроса
                print(f"[{self._time()}] Ввод: '{SEARCH_QUERY}'")
                sb.type(search_input, SEARCH_QUERY)
                self._delay(1, 2)

                # Клик по кнопке
                print(f"[{self._time()}] Клик по кнопке...")
                btn_selectors = [
                    'button[aria-label="Поиск"]',
                    'button[type="submit"]',
                    'button[class*="search"]',
                ]
                clicked = False
                for btn_sel in btn_selectors:
                    if sb.is_element_visible(btn_sel):
                        sb.click(btn_sel)
                        print(f"  ✅ Клик: {btn_sel}")
                        clicked = True
                        break
                if not clicked:
                    encoded = SEARCH_QUERY.replace(' ', '%20')
                    sb.open(f"https://www.ozon.ru/search/?text={encoded}&from_global=true")
                    print("  ⚠️ Прямой URL")

                # Ждём загрузки
                print(f"[{self._time()}] Ожидание загрузки...")
                self._delay(6, 10)

                # === СКРОЛЛ И НАКОПЛЕНИЕ SKU ===
                print(f"[{self._time()}] Скролл ({MAX_SCROLLS} раз по {SCROLL_SIZE}px)...")

                all_skus = []
                seen_skus = set()
                position = 0
                pos_on_current_scroll = 0

                for scroll_num in range(1, MAX_SCROLLS + 1):
                    html = sb.get_page_source()
                    new_skus = self._extract_skus(html)

                    added = 0
                    pos_on_current_scroll = 0

                    for sku in new_skus:
                        if sku not in seen_skus:
                            seen_skus.add(sku)
                            all_skus.append(sku)
                            position += 1
                            pos_on_current_scroll += 1
                            added += 1

                            # ПРОВЕРКА
                            if sku == TARGET_SKU:
                                print(f"\n{'=' * 50}")
                                print(f"  ✅ НАЙДЕН!")
                                print(f"  📍 Позиция: {position}")
                                print(f"  🔄 Скролл: {scroll_num}/{MAX_SCROLLS}")
                                print(f"  📦 Всего проверено: {len(all_skus)}")
                                print(f"{'=' * 50}")
                                return CheckResult(
                                    ts, SEARCH_QUERY, TARGET_SKU, True,
                                    position, scroll_num, pos_on_current_scroll, len(all_skus)
                                )

                    print(f"    Скролл {scroll_num:2d}/{MAX_SCROLLS}: +{added:2d} новых | Всего: {len(all_skus)}")

                    # Дополнительная проверка если ничего не добавилось
                    if added == 0:
                        time.sleep(1)
                        html = sb.get_page_source()
                        new_skus = self._extract_skus(html)
                        for sku in new_skus:
                            if sku not in seen_skus:
                                seen_skus.add(sku)
                                all_skus.append(sku)
                                position += 1
                                pos_on_current_scroll += 1
                                added += 1
                                if sku == TARGET_SKU:
                                    print(f"\n{'=' * 50}")
                                    print(f"  ✅ НАЙДЕН!")
                                    print(f"  📍 Позиция: {position}")
                                    print(f"{'=' * 50}")
                                    return CheckResult(
                                        ts, SEARCH_QUERY, TARGET_SKU, True,
                                        position, scroll_num, pos_on_current_scroll, len(all_skus)
                                    )

                        if added == 0 and scroll_num > 5:
                            print(f"    [INFO] Конец выдачи")
                            break

                    # Скроллим
                    self._scroll(sb, SCROLL_SIZE)
                    time.sleep(SCROLL_PAUSE)

                # Не нашли
                print(f"\n  ❌ Не найден. Проверено SKU: {len(all_skus)}")
                return CheckResult(
                    ts, SEARCH_QUERY, TARGET_SKU, False,
                    0, 0, 0, len(all_skus), f"Не найден в {len(all_skus)} товарах"
                )

        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()
            return CheckResult(ts, SEARCH_QUERY, TARGET_SKU, False, 0, 0, 0, 0, str(e))

    def save(self, result: CheckResult):
        file_exists = os.path.exists(LOG_FILE)
        with open(LOG_FILE, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'timestamp', 'query', 'sku', 'found', 'position',
                'scroll_num', 'pos_on_scroll', 'total_scrolled', 'error'
            ])
            if not file_exists:
                writer.writeheader()
            writer.writerow(asdict(result))
        print(f"  [LOG] Сохранено в {LOG_FILE}")

    def _time(self):
        return datetime.now().strftime("%H:%M:%S")

    def run(self):
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║  OZON MONITOR — Лог: номер скролла                          ║
║  Товар: {TARGET_SKU}                                         ║
║  Запрос: {SEARCH_QUERY}                                      ║
╚══════════════════════════════════════════════════════════════╝
        """)

        while True:
            result = self.check()
            self.save(result)

            status = "✅" if result.found else "❌"
            if result.found:
                print(f"[{self._time()}] {status} Позиция: {result.position} | Скролл: {result.scroll_num}")
            else:
                print(f"[{self._time()}] {status} {result.error or 'Не найден'}")

            print(f"[{self._time()}] Следующая проверка через {CHECK_INTERVAL // 60} мин...")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor = OzonMonitor()
    try:
        monitor.run()
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Остановлено")