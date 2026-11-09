"""آزمون رفتار واقعی صفحه با ماوس و کلیک."""

import re


def test_page_is_persian_rtl_with_local_font(app):
    page = app.page
    assert page.get_attribute("html", "dir") == "rtl"
    assert page.evaluate("document.fonts.load('16px Vazirmatn').then(() => document.fonts.check('16px Vazirmatn'))")


def test_no_request_leaves_this_computer(browser, server):
    context = browser.new_context()
    page = context.new_page()
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(server)
    page.wait_for_load_state("networkidle")
    context.close()
    assert requests and all(u.startswith(server) or u.startswith("data:") for u in requests)


def test_add_course_from_dialog(app):
    page = app.page
    page.click("#add-button")
    page.click('[data-add="study"]')
    page.click("#add-no-template")
    page.fill('#item-form [name="title"]', "الگوریتم")
    page.fill('#item-form [name="session_count"]', "3")
    page.click("#save-item")
    app.settle()
    assert app.titles() == ["الگوریتم"]
    assert app.day_tasks() == ["الگوریتم"]


def test_add_routine_and_custom_type(app):
    page = app.page
    page.click("#add-button")
    page.click('[data-add="type"]')
    page.fill('#type-form [name="name"]', "پروژه")
    page.click('#type-form button[type="submit"]')
    app.settle()
    page.click("#add-button")
    page.click(".add-tile.typed")
    assert "پروژه" in page.inner_text("#item-dialog-title")
    page.fill('#item-form [name="title"]', "سایت")
    page.click("#save-item")
    app.settle()
    assert page.locator(".chip.typed").inner_text() == "پروژه"


def test_drag_course_changes_queue_and_calendar_live(app):
    app.add("اول")
    app.add("دوم")
    app.add("سوم")
    app.reload()
    assert app.day_tasks() == ["اول", "دوم"]
    handle = app.page.locator(".item .handle").nth(2)
    top = app.page.locator(".item").first.bounding_box()
    mouse = app.drag(handle, top["x"] + top["width"] - 10, top["y"] + 4)
    assert app.page.locator(".item.lifted").count() == 1          # خود کارت بلند شده
    mouse.up()
    app.settle()
    assert app.titles() == ["سوم", "اول", "دوم"]
    assert app.day_tasks() == ["سوم", "اول"]                       # تقویم بدون reload عوض شد
    assert app.page.locator(".item.lifted").count() == 0
    app.reload()
    assert app.titles() == ["سوم", "اول", "دوم"]                   # ذخیره شده


def test_drag_releases_manual_move_of_that_course(app):
    app.add("اول")
    state = app.add("دوم")
    second = next(i for i in state["items"] if i["title"] == "دوم")
    later = state["plan"]["days"][0]["date"]
    app.call("POST", "/api/tasks/move", {"session_id": second["sessions"][0]["id"], "kind": "read", "date": later})
    app.reload()
    assert app.page.locator(".item .pinned").count() == 1
    app.page.click(".item .pinned button.link")
    app.settle()
    assert app.page.locator(".item .pinned").count() == 0


def test_drag_task_to_another_day(app):
    app.add("اول")
    app.reload()
    chip = app.page.locator(".cal-day.today .task").first
    columns = app.page.locator(".week-day")
    today_index = app.page.evaluate("[...document.querySelectorAll('.week-day')].findIndex(d => d.classList.contains('today'))")
    if today_index == 6:
        app.page.click("#cal-next")
        app.page.click("#cal-prev")
        return    # جمعه آخرین ستون است؛ ستون بعدی در این هفته نیست
    target = columns.nth(today_index + 1).bounding_box()
    mouse = app.drag(chip, target["x"] + target["width"] / 2, target["y"] + target["height"] / 2)
    assert app.page.locator(".task.ghost").count() == 1
    assert app.page.locator(".cal-day.drop-target").count() == 1
    mouse.up()
    app.settle()
    assert app.day_tasks() == []
    assert app.page.locator(".task.ghost").count() == 0
    assert "📌" in columns.nth(today_index + 1).inner_text()


def test_tick_then_mark_not_done(app):
    app.add("اول", count=2)
    app.reload()
    app.page.click(".cal-day.today .task .tick")
    app.settle()
    assert app.done_tasks() == ["✓ اول"]
    assert app.day_tasks() == []                       # سرعت: جلسهٔ دوم امروز نمی‌آید
    app.page.click(".cal-day.today .task.done")
    app.page.click('#popover button:has-text("انجام نشده")')
    app.settle()
    assert app.done_tasks() == []
    assert app.day_tasks() == ["اول"]


def test_undo_and_redo_with_counters(app):
    page = app.page
    page.click("#add-button")
    page.click('[data-add="study"]')
    page.click("#add-no-template")
    page.fill('#item-form [name="title"]', "الف")
    page.click("#save-item")
    app.settle()
    assert page.inner_text("#undo-button .count") == "۱"
    page.click("#undo-button")
    app.settle()
    assert app.titles() == []
    assert page.inner_text("#redo-button .count") == "۱"
    page.click("#redo-button")
    app.settle()
    assert app.titles() == ["الف"]
    assert page.inner_text("#redo-button .count") == ""


def test_category_tabs(app):
    page = app.page
    page.click(".cat-tab.plus")
    page.fill("#category-tabs input", "زبان")
    page.press("#category-tabs input", "Enter")
    app.settle()
    assert "زبان" in page.locator(".cat-tab .name").all_inner_texts()
    page.dblclick('.cat-tab:has-text("زبان")')
    page.fill("#category-tabs input", "ریاضی")
    page.press("#category-tabs input", "Enter")
    app.settle()
    assert "ریاضی" in page.locator(".cat-tab .name").all_inner_texts()
    page.hover('.cat-tab:has-text("ریاضی")')
    page.click('.cat-tab:has-text("ریاضی") .x')
    app.settle()
    assert "ریاضی" not in page.locator(".cat-tab .name").all_inner_texts()


def test_views_and_navigation(app):
    app.add("اول", count=2)
    page = app.page
    app.reload()
    page.click("#view-day")
    assert page.locator(".day-column").count() == 1
    first_title = page.inner_text("#cal-title")
    page.click("#cal-next")
    assert page.inner_text("#cal-title") != first_title
    page.click("#cal-today")
    page.click("#view-month")
    assert page.locator(".month-day").count() >= 29
    page.click("#view-week")
    assert page.locator(".week-day").count() == 7


def test_far_future_days_show_their_tasks(app):
    # کار خیلی دور باید با رفتن به همان ماه دیده شود
    app.add("دور", count=1, minutes=60, review_intervals=[200])
    page = app.reload().page
    page.click("#view-month")
    for _ in range(7):
        page.click("#cal-next")
    app.settle()
    assert page.locator('.month-day .task-title:has-text("دور")').count() == 1


def test_select_course_highlights_days(app):
    app.add("اول", count=2)
    app.reload()
    app.page.click(".item .title")
    assert app.page.locator(".cal-day.has-selected").count() >= 1


def test_note_shows_on_task_and_search_finds_it(app):
    app.add("اول")
    page = app.reload().page
    page.click(".cal-day.today .task .task-meta")
    page.fill("#popover textarea", "سؤال مهم")
    page.keyboard.press("Tab")
    app.settle()
    page.keyboard.press("Escape")
    assert "📝" in page.inner_text(".cal-day.today .task")
    app.add("دوم")
    app.reload()
    page.fill("#item-search", "سؤال")
    app.settle()
    assert app.titles() == ["اول"]
    page.fill("#item-search", "")
    app.settle()
    assert app.titles() == ["اول", "دوم"]


def test_bulk_add(app):
    page = app.page
    page.click("#add-button")
    page.click('[data-add="bulk"]')
    page.fill('#bulk-form [name="text"]', "آمار، ۲، ۳۰\nتاریخ")
    page.click('#bulk-form button[type="submit"]')
    app.settle()
    assert app.titles() == ["آمار", "تاریخ"]


def test_dependency_from_dialog(app):
    app.add("پیش‌نیاز", count=2)
    app.add("بعدی")
    page = app.reload().page
    page.locator('.item:has-text("بعدی") button[title="ویرایش"]').click()
    page.click("#requires-add")
    page.click("#save-item")
    app.settle()
    assert "🔒" in page.locator('.item:has-text("بعدی") .meta').inner_text()


def test_template_save_and_use(app):
    page = app.page
    page.click("#add-button")
    page.click('[data-add="study"]')
    page.click("#add-no-template")
    page.fill('#item-form [name="session_count"]', "7")
    page.click("#template-save")
    app.settle()
    page.fill('#item-form [name="session_count"]', "1")
    page.select_option("#template-select", label="الگوی آزمایشی")
    assert page.input_value('#item-form [name="session_count"]') == "7"
    page.click("#close-item")


def test_archive_finished_course(app):
    state = app.add("تمام", review_intervals=[1])
    sid = state["items"][0]["sessions"][0]["id"]
    app.call("POST", "/api/tasks/done", {"session_id": sid, "kind": "read"})
    app.call("POST", "/api/tasks/done", {"session_id": sid, "kind": "review"})
    page = app.reload().page
    page.click('.item button[title="بایگانی"]')
    app.settle()
    assert app.titles() == []
    page.click('#status-tabs button:has-text("بایگانی")')
    assert app.titles() == ["تمام"]


def test_day_menu_vacation(app):
    app.add("اول")
    page = app.reload().page
    page.click(".cal-day.today .day-head")
    page.click('#popover button:has-text("تعطیل کردن بازه")')
    app.settle()
    assert "off" in page.get_attribute(".cal-day.today", "class")
    assert app.day_tasks() == []
    page.click("#undo-button")
    app.settle()
    assert app.day_tasks() == ["اول"]


def test_settings_slider_chart_and_save(app):
    page = app.page
    page.click("#settings-button")
    assert "۳۳٪" in page.inner_text("#ratio-value")
    page.locator('[name="ratio_percent"]').fill("50")
    assert "۳۰ دقیقه" in page.inner_text("#ratio-explain")
    assert page.locator("#interval-chart .point").count() == 4
    page.click("#interval-remove")
    assert page.locator("#interval-chart .point").count() == 3
    assert page.locator("#interval-explain li").count() == 3
    before = page.inner_text("#chart-length-label")
    page.click("#chart-longer")
    assert page.inner_text("#chart-length-label") != before
    # کشیدن واقعی نقطه روی نمودار
    point = page.locator('#interval-chart .point[data-index="1"] circle').bounding_box()
    page.mouse.move(point["x"] + 5, point["y"] + 5)
    page.mouse.down()
    page.mouse.move(point["x"] - 40, point["y"] + 5, steps=6)
    page.mouse.up()
    page.locator("#interval-presets button").nth(1).click()
    page.select_option('[name="font_family"]', "Shabnam")
    page.click('#settings-form button[type="submit"]')
    app.settle()
    assert page.evaluate("getComputedStyle(document.body).fontFamily").startswith("Shabnam")
    state = app.call("GET", "/api/state")
    assert state["settings"]["review_intervals"] == [1, 2, 4, 7]
    assert state["settings"]["default_review_ratio"] == "50/100"


def test_color_mode_by_source(app):
    app.add("اول", color="#123456")
    page = app.reload().page
    page.click("#settings-button")
    page.check('[name="color_mode"][value="source"]')
    assert page.locator("#source-colors li").count() == 1
    page.click('#settings-form button[type="submit"]')
    app.settle()
    style = page.locator(".cal-day.today .task").first.get_attribute("style")
    assert "#123456" in style


def test_dark_theme_is_kept_after_reload(app):
    page = app.page
    page.click("#settings-button")
    page.select_option('[name="theme"]', "dark")
    page.click('#settings-form button[type="submit"]')
    app.settle()
    app.reload()
    assert page.get_attribute("html", "data-theme") == "dark"


def test_splitter_resizes_columns(app):
    page = app.page
    before = page.locator(".sources").bounding_box()["width"]
    box = page.locator("#splitter").bounding_box()
    page.mouse.move(box["x"] + 6, box["y"] + 100)
    page.mouse.down()
    page.mouse.move(box["x"] - 100, box["y"] + 100, steps=5)
    page.mouse.up()
    assert page.locator(".sources").bounding_box()["width"] > before + 50


def test_report_tabs(app):
    state = app.add("اول")
    app.call("POST", "/api/tasks/done", {"session_id": state["items"][0]["sessions"][0]["id"], "kind": "read"})
    page = app.reload().page
    page.click("#stats-button")
    page.wait_for_selector(".stat-tile")
    assert page.locator(".bars-chart .bar").count() == 12
    page.click('#report-tabs button:has-text("ماهانه")')
    page.wait_for_function("document.querySelector('.stats-section h3').textContent.length > 0")
    app.settle()
    assert page.locator(".bars-chart .bar").count() == 12
    page.click('#report-tabs button:has-text("کلی")')
    app.settle()
    assert page.locator(".heat").count() > 300
    assert re.search("روز فعال", page.inner_text("#stats-body"))


def test_export_menu_builds_file(app, tmp_path):
    app.add("اول")
    app.call("PATCH", "/api/settings", {"export_folder": str(tmp_path / "out")})
    page = app.reload().page
    page.click("#export-button")
    page.click('#popover button:has-text("ساختن خروجی")')
    page.wait_for_selector('#popover .pop-title:has-text("ذخیره شد")')
    assert list((tmp_path / "out").glob("*.html"))


def test_backup_list_and_restore(app):
    page = app.page
    page.click("#settings-button")
    page.wait_for_selector("#backup-list button")
    app.add("بعد از backup")
    page.click("#backup-list button")
    app.settle()
    state = app.call("GET", "/api/state")
    assert state["items"] == []


def test_vacation_range_shows_when_there_is_no_work(app):
    """بدون هیچ درسی برنامه فقط امروز را دارد؛ روزهای بعدی بازهٔ تعطیلی هم باید تعطیل دیده شوند."""
    page = app.page
    page.click(".cal-day.today .day-head")
    page.click('#popover button:has-text("تعطیل کردن بازه")')
    app.settle()
    page.click("#view-month")
    app.settle()
    assert page.locator(".cal-day.off").count() >= 7
    assert page.locator('.cal-day.off .small:has-text("تعطیل")').count() >= 7


def test_remove_reviews_button(app):
    app.add("اول")
    page = app.reload().page
    page.click(".item .actions button.icon")
    page.click("#remove-reviews")
    app.settle()
    assert page.is_hidden("#remove-reviews")
    assert page.is_visible("#restore-reviews")
    page.click("#close-item")
    assert page.locator(".task.kind-review").count() == 0


def test_all_view_shows_plan_until_last_review(app):
    app.add("اول", count=2)
    page = app.reload().page
    total = page.evaluate("fetch('/api/state').then(r => r.json()).then(s => s.plan.total_days)")
    page.click("#view-all")
    app.settle()
    assert page.locator(".all-day").count() == total
    assert page.locator(".all-day .task.kind-review").count() == 8


def test_kind_filter_hides_and_remembers(app):
    app.add("اول", count=1)
    page = app.reload().page
    page.click("#view-all")
    app.settle()
    assert page.locator(".task.kind-review").count() == 4
    page.uncheck(".legend-toggle.kind-review input")
    assert page.locator(".task.kind-review").count() == 0
    assert page.locator(".task.kind-read").count() == 1
    page.reload()
    page.wait_for_selector("#today:not(:empty)")
    page.click("#view-all")
    app.settle()
    assert page.locator(".task.kind-review").count() == 0


def test_horizontal_orientation(app):
    app.add("اول")
    page = app.reload().page
    page.click("#orient-horizontal")
    day = page.locator(".week .cal-day")
    first, second = day.nth(0).bounding_box(), day.nth(1).bounding_box()
    assert second["y"] > first["y"]
    assert abs(second["x"] - first["x"]) < 2
    page.click("#orient-vertical")
    assert day.nth(1).bounding_box()["y"] == day.nth(0).bounding_box()["y"]


def test_task_size_follows_minutes(app):
    app.add("بلند", minutes=100)
    app.add("کوتاه", minutes=10)
    page = app.reload().page
    long, short = page.locator(".cal-day.today .task.sized").nth(0), page.locator(".cal-day.today .task.sized").nth(1)
    assert long.bounding_box()["height"] > short.bounding_box()["height"] * 1.5


def test_day_header_text_stays_inside_narrow_column(app):
    app.add("اول", count=6)
    page = app.reload().page
    page.set_viewport_size({"width": 1000, "height": 700})
    app.settle()
    overflow = page.evaluate("[...document.querySelectorAll('.day-head')].filter(e => e.scrollWidth > e.clientWidth + 1).length")
    assert overflow == 0


def test_layout_modes(app):
    page = app.page
    assert page.is_visible(".sources") and page.is_visible(".calendar")
    page.click('#layout-tabs [data-layout="plan"]')
    assert page.is_hidden(".sources") and page.is_visible(".calendar")
    width = page.locator(".calendar").bounding_box()["width"]
    assert width > 1400
    page.click('#layout-tabs [data-layout="sources"]')
    assert page.is_visible(".sources") and page.is_hidden(".calendar")
    page.click('#layout-tabs [data-layout="stack"]')
    assert page.locator(".calendar").bounding_box()["y"] != page.locator(".sources").bounding_box()["y"]
    page.reload()
    page.wait_for_selector("#today:not(:empty)")
    assert page.get_attribute("body", "data-layout") == "stack"


def test_ui_scale_auto_by_window_width_and_manual(app):
    page = app.page

    def size():
        return page.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize)")

    page.set_viewport_size({"width": 2400, "height": 1200})
    page.wait_for_timeout(100)
    assert size() == 16
    page.set_viewport_size({"width": 1366, "height": 650})
    page.wait_for_timeout(100)
    assert size() == 16 * 0.8
    app.call("PATCH", "/api/settings", {"ui_scale": 150})
    app.reload()
    assert size() == 24


def test_add_menu_replaces_the_add_buttons(app):
    page = app.page
    assert page.inner_text(".sources h2") == "کارها و منابع"
    assert page.locator(".sources .panel-head button").count() == 1
    page.click("#add-button")
    labels = page.locator("#add-kinds .add-tile strong").all_inner_texts()
    assert labels == ["درس", "کار روتین", "کار یک‌باره", "پروژه", "چند درس با هم", "نوع تازه"]


def test_study_template_fills_the_form(app):
    page = app.page
    page.click("#add-button")
    page.click('[data-add="study"]')
    page.click('[data-template="study-10"]')
    fields = page.locator("#item-form")
    assert fields.locator('[name="session_count"]').input_value() == "10"
    assert fields.locator('[name="review_intervals"]').input_value() == "1، 3، 6"
    page.fill('#item-form [name="title"]', "فشرده")
    page.click("#save-item")
    app.settle()
    state = app.call("GET", "/api/state")
    assert state["items"][0]["review_intervals"] == [1, 3, 6]
    assert len(state["items"][0]["sessions"]) == 10


def test_once_task_on_chosen_day_has_no_reviews(app):
    page = app.page
    page.click("#add-button")
    page.click('[data-add="once"]')
    assert page.is_hidden("#item-form [data-sessions]")
    assert page.is_hidden('#item-form [name="review_ratio"]')
    page.fill('#item-form [name="title"]', "ثبت‌نام")
    page.click("#save-item")
    app.settle()
    state = app.call("GET", "/api/state")
    item = state["items"][0]
    assert (item["variant"], item["no_reviews"], len(item["sessions"])) == ("once", True, 1)
    assert page.locator(".task.kind-once").count() == 1
    assert "کار یک‌باره" in page.inner_text(".task.kind-once")
    page.click(".task.kind-once .tick")
    app.settle()
    state = app.call("GET", "/api/state")
    assert state["items"][0]["status_list"] == "finished"
    assert not [t for d in state["plan"]["days"] for t in d["tasks"]]


def test_project_runs_sessions_without_reviews_and_has_own_filter(app):
    page = app.page
    page.click("#add-button")
    page.click('[data-add="project"]')
    page.click('[data-template="project-5"]')
    page.fill('#item-form [name="title"]', "پایان‌نامه")
    page.click("#save-item")
    app.settle()
    state = app.call("GET", "/api/state")
    tasks = [t for d in state["plan"]["days"] for t in d["tasks"]]
    assert len(tasks) == 5 and {t["kind"] for t in tasks} == {"read"}
    assert page.is_visible(".legend-toggle.kind-project")


def test_templates_can_be_deleted_and_restored(app):
    page = app.page
    page.click("#settings-button")
    page.locator("#template-settings li", has_text="درس سه‌ماهه").locator("button").click()
    app.settle()
    state = app.call("GET", "/api/state")
    assert "study-90" not in [t["id"] for t in state["templates"]]
    page.click("#templates-restore")
    app.settle()
    state = app.call("GET", "/api/state")
    assert "study-90" in [t["id"] for t in state["templates"]]


def test_first_run_asks_language_and_calendar(browser, server):
    page = browser.new_context(viewport={"width": 1600, "height": 1000}, locale="de-DE").new_page()
    page.goto(server)
    page.wait_for_selector("#setup-dialog[open]")
    assert page.input_value("#setup-form [name=language]") == "de"
    assert page.input_value("#setup-form [name=calendar]") == "gregorian"
    page.keyboard.press("Escape")
    assert page.is_visible("#setup-dialog")
    with page.expect_navigation():
        page.click("#setup-form button[type=submit]")
    page.wait_for_selector("#today:not(:empty)")
    assert page.get_attribute("html", "dir") == "ltr"
    assert page.inner_text(".sources h2") == "Aufgaben und Quellen"
    assert page.is_hidden("#setup-dialog")
    assert page.inner_text("#undo-button .count") == ""
    page.context.close()


def test_changing_language_in_settings_reloads_translated(app):
    page = app.page
    page.click("#settings-button")
    page.select_option("#settings-form [name=language]", "ar")
    with page.expect_navigation():
        page.click('#settings-form button[type="submit"]')
    page.wait_for_selector("#today:not(:empty)")
    assert page.get_attribute("html", "dir") == "rtl"
    assert page.inner_text(".sources h2") == "المهام والمصادر"


def test_gregorian_calendar_week_starts_on_chosen_day(app):
    app.call("PATCH", "/api/settings", {"language": "en", "calendar": "gregorian", "first_weekday": 0})
    page = app.open().page
    assert page.locator(".week .cal-day .weekday").first.inner_text() == "Monday"
    assert page.locator(".week .cal-day .weekday").last.inner_text() == "Sunday"
    page.click("#view-month")
    assert page.locator(".month-head").first.inner_text() == "Monday"
    import re
    assert re.fullmatch(r"[A-Z][a-z]+ \d{4}", page.inner_text("#cal-title"))


def test_no_persian_text_left_on_page_in_english(app):
    app.call("PATCH", "/api/settings", {"language": "en", "calendar": "gregorian", "first_weekday": 0})
    app.add("Algebra", count=2)
    page = app.open().page
    app.settle()
    left = page.evaluate(r"""(() => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const found = [];
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (/[\u0600-\u06FF]/.test(n.textContent) && !n.parentElement.closest("script, style")) found.push(n.textContent.trim());
      }
      return found;
    })()""")
    assert left == []


def test_whats_new_shows_once_after_update(app):
    app.add("اول")
    app.call("PATCH", "/api/settings", {"last_seen_version": "1.0.0"})
    page = app.open().page
    page.wait_for_selector("#whats-new-dialog[open]")
    assert "ناعدد" not in page.inner_text("#whats-new-title")
    assert re.search(r"[۰-۹]\.[۰-۹]\.[۰-۹]", page.inner_text("#whats-new-title"))
    assert page.locator("#whats-new-list li").count() > 3
    page.click("#close-whats-new")
    app.settle()
    page = app.open().page
    app.settle()
    assert page.is_hidden("#whats-new-dialog")


def test_version_label_and_no_update_button_when_up_to_date(app):
    page = app.page
    assert re.fullmatch(r"v\d+\.\d+\.\d+", page.inner_text("#app-version"))
    assert page.is_hidden("#update-button")


def test_update_button_and_dialog_with_a_fake_release(app):
    page = app.page
    release = {"available": True, "latest": "9.9.9", "notes": "خلاصهٔ تغییرات", "asset": {"name": "a.dmg", "url": "x", "size": 2097152}}
    page.route("**/api/update/check*", lambda route: route.fulfill(json=release))
    app.open()
    page.wait_for_selector("#update-button:not([hidden])", timeout=5000)
    assert "۹.۹.۹" in page.inner_text("#update-button")
    page.click("#update-button")
    assert page.inner_text("#update-notes") == "خلاصهٔ تغییرات"
    assert page.is_visible("#update-download")
    page.click("#close-update")


def test_score_card_appears_in_weekly_report(app):
    state = app.add("اول")
    sid = state["items"][0]["sessions"][0]["id"]
    app.call("POST", "/api/tasks/done", {"session_id": sid, "kind": "read"})
    page = app.open().page
    page.click("#stats-button")
    page.wait_for_selector(".score-card")
    assert page.locator(".score-part").count() == 3
