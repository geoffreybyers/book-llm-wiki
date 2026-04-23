#!/usr/bin/env python3
"""LibraryThing catalog management tool.

Uses Scrapling (StealthyFetcher) to bypass Cloudflare and interact with
the LibraryThing catalog via browser automation. Persists browser session
to ~/.lt-session so Cloudflare/login only happens on first run.

Usage:
    python -m book_llm_wiki.downloader.librarything search "book title"
    python -m book_llm_wiki.downloader.librarything add "book title" "author"
    python -m book_llm_wiki.downloader.librarything delete <book_id>

All commands output JSON to stdout. Logs go to stderr.
"""

import sys
import os
import time
import json
from pathlib import Path

# Walk up from book_llm_wiki/downloader/librarything.py to the repo root
# (two levels up) so `.env` can be located regardless of invocation cwd.
REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = os.path.expanduser('~/.lt-session')


def log(msg):
    print(msg, file=sys.stderr)


def load_credentials():
    env_path = REPO_ROOT / '.env'
    creds = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if ':' in line:
                key, val = line.split(':', 1)
                creds[key.strip()] = val.strip()
    return creds


def is_logged_in(page):
    """Check if already logged in by looking for the Sign In button."""
    try:
        btn = page.locator('button:has-text("Sign In")')
        return btn.count() == 0 or not btn.first.is_visible()
    except:
        return True


def do_login(page, creds):
    """Login to LibraryThing if not already logged in."""
    page.wait_for_load_state('networkidle', timeout=15000)

    if is_logged_in(page):
        log("Already logged in (session reused)")
        return

    try:
        btn = page.locator('button:has-text("Sign In")')
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()
            time.sleep(1)
    except:
        pass

    uname = page.locator('input[name="formusername"]')
    for i in range(uname.count()):
        if uname.nth(i).is_visible():
            uname.nth(i).fill(creds['username'])
            pw = page.locator('input[name="formpassword"]')
            for j in range(pw.count()):
                if pw.nth(j).is_visible():
                    pw.nth(j).fill(creds['pass'])
                    pw.nth(j).press('Enter')
                    break
            break
    page.wait_for_load_state('networkidle', timeout=15000)
    time.sleep(3)
    log("Logged in")


def get_iframe(page):
    """Get the catalog bottom iframe, with retries."""
    iframe = page.frame('bottom')
    if not iframe:
        time.sleep(4)
        iframe = page.frame('bottom')
    return iframe


def extract_books_from_iframe(iframe):
    """Extract all books visible on the current iframe page."""
    return iframe.evaluate("""() => {
        const rows = document.querySelectorAll('tr[id^="catrow_"]');
        const books = [];
        for (const row of rows) {
            const titleEl = row.querySelector('a.lt-title');
            const authorEl = row.querySelector('a.lt-author');
            if (!titleEl) continue;

            const bookId = row.id.replace('catrow_', '');

            // Check collections from menu items
            const collections = [];
            const collMap = {1: 'library', 7: 'reading', 3: 'to_read', 5: 'read_unowned', 6: 'favorites'};
            for (const [cid, name] of Object.entries(collMap)) {
                const el = document.querySelector('#cm_' + bookId + '_' + cid);
                if (el && el.classList.contains('mbmiSelected')) {
                    collections.push(name);
                }
            }

            books.push({
                book_id: bookId,
                title: titleEl.innerText.trim(),
                author: authorEl ? authorEl.innerText.trim() : '',
                collections: collections
            });
        }
        return books;
    }""")


def scrape_all_catalog_pages(page, creds):
    """Scrape all pages of the catalog (all collections). Returns list of all books."""
    page.goto(f'https://www.librarything.com/catalog/{creds["username"]}')
    page.wait_for_load_state('networkidle', timeout=15000)
    time.sleep(4)

    # Switch iframe to "All collections" view (default shows "Your library" only)
    iframe = get_iframe(page)
    if iframe:
        iframe.evaluate("""() => {
            window.location.href = '/catalog_bottom.php?collection=-1&offset=0';
        }""")
        time.sleep(4)

    all_books = []
    offset = 0

    while True:
        iframe = get_iframe(page)
        if not iframe:
            log(f"No iframe at offset {offset}")
            break

        books = extract_books_from_iframe(iframe)
        if not books:
            break

        all_books.extend(books)
        log(f"Page offset={offset}: {len(books)} books (total: {len(all_books)})")

        # Check for next page
        has_next = iframe.evaluate("""() => {
            const links = document.querySelectorAll('a');
            for (const l of links) {
                if (l.innerText.trim() === 'next page') return true;
            }
            return false;
        }""")

        if not has_next:
            break

        offset += 20
        iframe.evaluate(f"""() => {{
            window.location.href = '/catalog_bottom.php?collection=-1&offset={offset}';
        }}""")
        time.sleep(3)

    return all_books


def cmd_search(query):
    """Search the catalog for books matching query (case-insensitive title/author match)."""
    from scrapling import StealthyFetcher

    creds = load_credentials()
    result_holder = [None]

    def action(page):
        do_login(page, creds)

        all_books = scrape_all_catalog_pages(page, creds)

        # Filter by query
        q = query.lower()
        matches = [b for b in all_books if q in b['title'].lower() or q in b['author'].lower()]

        log(f"Catalog total: {len(all_books)}, matches for '{query}': {len(matches)}")
        result_holder[0] = {
            'query': query,
            'results': matches,
            'count': len(matches),
            'catalog_total': len(all_books)
        }

    StealthyFetcher.fetch(
        'https://www.librarything.com/',
        headless=True,
        solve_cloudflare=True,
        page_action=action,
        wait=2000,
        network_idle=True,
        user_data_dir=SESSION_DIR
    )

    output = result_holder[0] or {'query': query, 'results': [], 'error': 'Action did not complete'}
    print(json.dumps(output, indent=2))


def cmd_add(title, author):
    """Add a book to LibraryThing in Your Library."""
    from scrapling import StealthyFetcher

    creds = load_credentials()
    result_holder = [None]

    def action(page):
        do_login(page, creds)

        # Navigate to add books page
        page.goto('https://www.librarything.com/addbooks')
        page.wait_for_load_state('networkidle', timeout=15000)
        time.sleep(2)

        # Ensure "Your library" (collection 1) is checked and others are unchecked
        checkboxes = page.locator('input[name="books_collections[]"]')
        for i in range(checkboxes.count()):
            cb = checkboxes.nth(i)
            val = cb.get_attribute('value')
            try:
                if val == '1':
                    if not cb.is_checked():
                        cb.check()
                else:
                    if cb.is_checked():
                        cb.uncheck()
            except:
                pass

        # Search for the book
        search_query = f'{title} {author}' if author else title
        page.fill('#form_find', search_query)
        page.click('#search_btn')
        time.sleep(8)

        # Click first result
        first = page.locator('.addbooks_title a').first
        if first.count() > 0:
            matched_text = first.inner_text().strip()
            first.click()
            time.sleep(3)
            log(f"Added: {matched_text}")
            result_holder[0] = {
                'status': 'added',
                'matched': matched_text,
                'collection': 'library',
                'search_query': search_query
            }
        else:
            log(f"No results for: {search_query}")
            result_holder[0] = {
                'status': 'not_found',
                'search_query': search_query
            }

    StealthyFetcher.fetch(
        'https://www.librarything.com/',
        headless=True,
        solve_cloudflare=True,
        page_action=action,
        wait=2000,
        network_idle=True,
        user_data_dir=SESSION_DIR
    )

    output = result_holder[0] or {'status': 'error', 'message': 'Action did not complete'}
    print(json.dumps(output, indent=2))


def cmd_delete(book_id):
    """Delete a book from the LibraryThing catalog."""
    from scrapling import StealthyFetcher

    creds = load_credentials()
    result_holder = [None]

    def action(page):
        page.on('dialog', lambda d: d.accept())
        do_login(page, creds)

        # Navigate to catalog to get iframe
        page.goto(f'https://www.librarything.com/catalog/{creds["username"]}')
        page.wait_for_load_state('networkidle', timeout=15000)
        time.sleep(4)

        iframe = get_iframe(page)
        if not iframe:
            result_holder[0] = {'status': 'error', 'message': 'No catalog iframe found'}
            return

        # Navigate the iframe to the delete URL
        iframe.evaluate(f"""() => {{
            window.location.href = 'deletebook.php?deleteid={book_id}';
        }}""")
        time.sleep(3)

        # Verify deletion by reloading catalog
        page.goto(f'https://www.librarything.com/catalog/{creds["username"]}')
        page.wait_for_load_state('networkidle', timeout=15000)
        time.sleep(4)

        iframe2 = get_iframe(page)
        if iframe2:
            still_exists = iframe2.evaluate(f"""() => {{
                return !!document.getElementById('catrow_{book_id}');
            }}""")
            if not still_exists:
                log(f"Deleted book {book_id}")
                result_holder[0] = {'status': 'deleted', 'book_id': book_id}
            else:
                result_holder[0] = {'status': 'error', 'message': f'Book {book_id} still exists'}
        else:
            result_holder[0] = {'status': 'unknown', 'message': 'Could not verify deletion'}

    StealthyFetcher.fetch(
        'https://www.librarything.com/',
        headless=True,
        solve_cloudflare=True,
        page_action=action,
        wait=2000,
        network_idle=True,
        user_data_dir=SESSION_DIR
    )

    output = result_holder[0] or {'status': 'error', 'message': 'Action did not complete'}
    print(json.dumps(output, indent=2))


def main():
    if len(sys.argv) < 2:
        print('Usage: python -m book_llm_wiki.downloader.librarything <command> [args...]', file=sys.stderr)
        print('Commands:', file=sys.stderr)
        print('  search "book title"                     - Search catalog', file=sys.stderr)
        print('  add "title" "author"                      - Add book to Your Library', file=sys.stderr)
        print('  delete <book_id>                        - Delete book', file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == 'search':
        if len(sys.argv) < 3:
            print('Usage: python -m book_llm_wiki.downloader.librarything search "book title"', file=sys.stderr)
            sys.exit(1)
        cmd_search(sys.argv[2])

    elif command == 'add':
        if len(sys.argv) < 4:
            print('Usage: python -m book_llm_wiki.downloader.librarything add "title" "author"', file=sys.stderr)
            sys.exit(1)
        cmd_add(sys.argv[2], sys.argv[3])

    elif command == 'delete':
        if len(sys.argv) < 3:
            print('Usage: python -m book_llm_wiki.downloader.librarything delete <book_id>', file=sys.stderr)
            sys.exit(1)
        cmd_delete(sys.argv[2])

    else:
        print(f'Unknown command: {command}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
