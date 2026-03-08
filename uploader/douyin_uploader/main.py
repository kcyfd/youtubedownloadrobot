from datetime import datetime
import os
import asyncio

from playwright.async_api import Playwright, async_playwright, Page

from conf import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
from utils.log import douyin_logger


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=LOCAL_CHROME_HEADLESS)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/creator-micro/content/upload")
        try:
            await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload", timeout=5000)
        except Exception:
            print("[+] 等待5秒 cookie 失效")
            await context.close()
            await browser.close()
            return False
        # 若仍处于登录界面或未出现上传控件，则视为 cookie 失效
        try:
            if await page.get_by_text("手机号登录").count() or await page.get_by_text("扫码登录").count():
                print("[+] 等待5秒 cookie 失效（检测到登录入口）")
                await context.close()
                await browser.close()
                return False
            # 核心判定：上传页必须存在文件选择 input，否则认为登录未生效
            file_input = page.locator("input[type='file']").first
            if not await file_input.count():
                print("[+] 等待5秒 cookie 失效（未找到上传控件）")
                await context.close()
                await browser.close()
                return False
        except Exception:
            await context.close()
            await browser.close()
            return False

        print("[+] cookie 有效")
        await context.close()
        await browser.close()
        return True


async def douyin_setup(account_file, handle=False, check_cookie=True):
    """若 check_cookie=False，仅检查 account_file 是否存在，不打开浏览器做 cookie 校验（上传时会再开浏览器，届时再发现 cookie 失效）。"""
    if not os.path.exists(account_file):
        if not handle:
            return False
        douyin_logger.info(
            "[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件"
        )
        await douyin_cookie_gen(account_file)
        return True
    if not check_cookie:
        return True
    if not await cookie_auth(account_file):
        if not handle:
            return False
        douyin_logger.info(
            "[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件"
        )
        await douyin_cookie_gen(account_file)
    return True


async def douyin_cookie_gen(account_file):
    async with async_playwright() as playwright:
        options = {"headless": LOCAL_CHROME_HEADLESS}
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context()
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/")

        # 这里不再打开 Playwright 调试器，而是让你在普通浏览器窗口中完成登录，
        # 然后在命令行按回车继续，最后保存 cookies 到 account_file。
        print(
            "\n[*] 已打开抖音创作者中心登录页，请在浏览器中完成登录（扫码或密码登录），\n"
            "    直到页面进入创作者中心主页或上传后台，然后回到当前命令行窗口。"
        )
        input("[*] 登录完成后按回车继续保存登录状态...")

        await context.storage_state(path=account_file)
        await context.close()
        await browser.close()


class DouYinVideo(object):
    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date: datetime,
        account_file,
        thumbnail_path=None,
        productLink="",
        productTitle="",
    ):
        self.title = title
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = "%Y年%m月%d日 %H:%M"
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = LOCAL_CHROME_HEADLESS
        self.thumbnail_path = thumbnail_path
        self.productLink = productLink
        self.productTitle = productTitle

    async def set_schedule_time_douyin(self, page, publish_date):
        label_element = page.locator("[class^='radio']:has-text('定时发布')")
        await label_element.click()
        await asyncio.sleep(1)
        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")
        await asyncio.sleep(1)
        await page.locator('.semi-input[placeholder="日期和时间"]').click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)

    async def handle_upload_error(self, page):
        douyin_logger.info("视频出错了，重新上传中")
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def upload(self, playwright: Playwright) -> bool:
        if self.local_executable_path:
            browser = await playwright.chromium.launch(
                headless=self.headless, executable_path=self.local_executable_path
            )
        else:
            browser = await playwright.chromium.launch(headless=self.headless)
        context = await browser.new_context(storage_state=f"{self.account_file}")
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/creator-micro/content/upload")
        douyin_logger.info(f"[+]正在上传-------{self.title}.mp4")
        douyin_logger.info("[-] 正在打开主页...")
        await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload")

        # 如果仍然停留在登录页，提示用户先完成登录
        # 通过手机号输入框占位符来判断，兼容文案变化
        try:
            login_phone_input = page.get_by_placeholder("请输入手机号")
            if await login_phone_input.count():
                douyin_logger.error(
                    "检测到当前页面是登录页，请先运行 python douyin_login.py 完成登录，再重新执行上传。"
                )
                await context.close()
                await browser.close()
                return False
        except Exception:
            # 忽略占位符选择器异常，继续后续流程
            pass

        # 更精确地定位上传视频的文件选择框，避免 strict mode 报错
        file_input = page.locator("input[type='file']").first
        if not await file_input.count():
            # 兼容旧页面结构
            file_input = page.locator("div[class^='container'] input[type='file']").first
        if not await file_input.count():
            douyin_logger.error("未找到上传视频的文件选择框，页面可能已改版或尚未登录。")
            await context.close()
            await browser.close()
            return False
        await file_input.set_input_files(self.file_path)

        while True:
            try:
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/publish?enter_from=publish_page",
                    timeout=3000,
                )
                douyin_logger.info("[+] 成功进入version_1发布页面!")
                break
            except Exception:
                try:
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
                        timeout=3000,
                    )
                    douyin_logger.info("[+] 成功进入version_2发布页面!")
                    break
                except Exception:
                    print("  [-] 超时未进入视频发布页面，重新尝试...")
                    await context.close()
                    await browser.close()
                    douyin_logger.info("  [-] 关闭浏览器，30秒后重试...")
                    await asyncio.sleep(30)
                    # 重新启动浏览器并从头执行上传入口
                    if self.local_executable_path:
                        browser = await playwright.chromium.launch(
                            headless=self.headless, executable_path=self.local_executable_path
                        )
                    else:
                        browser = await playwright.chromium.launch(headless=self.headless)
                    context = await browser.new_context(storage_state=f"{self.account_file}")
                    context = await set_init_script(context)
                    page = await context.new_page()
                    await page.goto("https://creator.douyin.com/creator-micro/content/upload")
                    douyin_logger.info("[-] 正在打开主页...")
                    await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload")
                    try:
                        login_phone_input = page.get_by_placeholder("请输入手机号")
                        if await login_phone_input.count():
                            douyin_logger.error(
                                "检测到当前页面是登录页，请先运行 python douyin_login.py 完成登录，再重新执行上传。"
                            )
                            await context.close()
                            await browser.close()
                            return False
                    except Exception:
                        pass
                    file_input = page.locator("input[type='file']").first
                    if not await file_input.count():
                        file_input = page.locator("div[class^='container'] input[type='file']").first
                    if not await file_input.count():
                        douyin_logger.error("未找到上传视频的文件选择框，页面可能已改版或尚未登录。")
                        await context.close()
                        await browser.close()
                        return False
                    await file_input.set_input_files(self.file_path)

        await asyncio.sleep(1)
        douyin_logger.info("  [-] 正在填充标题和话题...")

        title_input = None
        title_container = (
            page.get_by_text("作品标题")
            .locator("..")
            .locator("xpath=following-sibling::div[1]")
            .locator("input")
        )
        if await title_container.count():
            title_input = title_container.first
        if title_input is None:
            by_placeholder = page.locator('input[placeholder*="标题"]').first
            if await by_placeholder.count():
                title_input = by_placeholder
        if title_input is None:
            by_label_block = page.get_by_text("作品标题").locator("../..").locator("input").first
            if await by_label_block.count():
                title_input = by_label_block
        if title_input is not None:
            await title_input.click()
            await asyncio.sleep(0.2)
            await title_input.fill("")
            await title_input.fill(self.title[:30])
            await asyncio.sleep(0.3)
            await title_input.evaluate("el => el.blur()")
        else:
            douyin_logger.warning("  [-] 未找到作品标题输入框，跳过标题")

        await asyncio.sleep(0.5)
        css_selector = ".zone-container"
        for index, tag in enumerate(self.tags, start=1):
            await page.type(css_selector, "#" + tag, delay=60)
            await page.press(css_selector, "Space")
            await asyncio.sleep(0.4)
        douyin_logger.info(f"总共添加{len(self.tags)}个话题")
        await asyncio.sleep(1)

        while True:
            try:
                number = await page.locator('[class^="long-card"] div:has-text("重新上传")').count()
                if number > 0:
                    douyin_logger.success("  [-]视频上传完毕")
                    break
                else:
                    douyin_logger.info("  [-] 正在上传视频中...")
                    await asyncio.sleep(2)
                    if await page.locator('div.progress-div > div:has-text("上传失败")').count():
                        douyin_logger.error("  [-] 发现上传出错了... 准备重试")
                        await self.handle_upload_error(page)
            except Exception:
                douyin_logger.info("  [-] 正在上传视频中...")
                await asyncio.sleep(2)

        if self.productLink and self.productTitle:
            douyin_logger.info("  [-] 正在设置商品链接...")
            await self.set_product_link(page, self.productLink, self.productTitle)
            douyin_logger.info("  [+] 完成设置商品链接...")

        await self.set_thumbnail(page, self.thumbnail_path)
        await self.set_location(page, "")

        third_part_element = '[class^="info"] > [class^="first-part"] div div.semi-switch'
        if await page.locator(third_part_element).count():
            if "semi-switch-checked" not in await page.eval_on_selector(
                third_part_element, "div => div.className"
            ):
                await page.locator(third_part_element).locator("input.semi-switch-native-control").click()

        if self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)

        await asyncio.sleep(1)
        while True:
            try:
                publish_button = page.get_by_role("button", name="发布", exact=True)
                if await publish_button.count():
                    await publish_button.click()
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/manage**", timeout=3000
                )
                douyin_logger.success("  [-]视频发布成功")
                break
            except Exception:
                await self.handle_auto_video_cover(page)
                douyin_logger.info("  [-] 视频正在发布中...")
                await page.screenshot(full_page=True)
                await asyncio.sleep(0.5)

        await context.storage_state(path=self.account_file)
        douyin_logger.success("  [-]cookie更新完毕！")
        await asyncio.sleep(2)
        await context.close()
        await browser.close()
        return True

    async def handle_auto_video_cover(self, page):
        if await page.get_by_text("请设置封面后再发布").first.is_visible():
            print("  [-] 检测到需要设置封面提示...")
            recommend_cover = page.locator('[class^="recommendCover-"]').first
            if await recommend_cover.count():
                print("  [-] 正在选择第一个推荐封面...")
                try:
                    await recommend_cover.click()
                    await asyncio.sleep(1)
                    confirm_text = "是否确认应用此封面？"
                    if await page.get_by_text(confirm_text).first.is_visible():
                        print(f"  [-] 检测到确认弹窗: {confirm_text}")
                        await page.get_by_role("button", name="确定").click()
                        print("  [-] 已点击确认应用封面")
                        await asyncio.sleep(1)
                    print("  [-] 已完成封面选择流程")
                    return True
                except Exception as e:
                    print(f"  [-] 选择封面失败: {e}")
        return False

    async def set_thumbnail(self, page: Page, thumbnail_path: str):
        if thumbnail_path:
            douyin_logger.info("  [-] 正在设置视频封面...")
            await page.click('text="选择封面"')
            await page.wait_for_selector("div.dy-creator-content-modal")
            await page.click('text="设置竖封面"')
            await page.wait_for_timeout(2000)
            await page.locator(
                "div[class^='semi-upload upload'] >> input.semi-upload-hidden-input"
            ).set_input_files(thumbnail_path)
            await page.wait_for_timeout(2000)
            await page.locator("div#tooltip-container button:visible:has-text('完成')").click()
            douyin_logger.info("  [+] 视频封面设置完成！")
            await page.wait_for_selector("div.extractFooter", state="detached")

    async def set_location(self, page: Page, location: str = ""):
        if not location:
            return
        await page.locator('div.semi-select span:has-text("输入地理位置")').click()
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(2000)
        await page.keyboard.type(location)
        await page.wait_for_selector('div[role="listbox"] [role="option"]', timeout=5000)
        await page.locator('div[role="listbox"] [role="option"]').first.click()

    async def handle_product_dialog(self, page: Page, product_title: str):
        await page.wait_for_timeout(2000)
        await page.wait_for_selector('input[placeholder="请输入商品短标题"]', timeout=10000)
        short_title_input = page.locator('input[placeholder="请输入商品短标题"]')
        if not await short_title_input.count():
            douyin_logger.error("[-] 未找到商品短标题输入框")
            return False
        product_title = product_title[:10]
        await short_title_input.fill(product_title)
        await page.wait_for_timeout(1000)
        finish_button = page.locator('button:has-text("完成编辑")')
        if "disabled" not in await finish_button.get_attribute("class"):
            await finish_button.click()
            douyin_logger.debug("[+] 成功点击'完成编辑'按钮")
            await page.wait_for_selector(".semi-modal-content", state="hidden", timeout=5000)
            return True
        else:
            douyin_logger.error("[-] '完成编辑'按钮处于禁用状态，尝试直接关闭对话框")
            cancel_button = page.locator('button:has-text("取消")')
            if await cancel_button.count():
                await cancel_button.click()
            else:
                close_button = page.locator(".semi-modal-close")
                await close_button.click()
            await page.wait_for_selector(".semi-modal-content", state="hidden", timeout=5000)
            return False

    async def set_product_link(self, page: Page, product_link: str, product_title: str):
        await page.wait_for_timeout(2000)
        try:
            await page.wait_for_selector("text=添加标签", timeout=10000)
            dropdown = (
                page.get_by_text("添加标签")
                .locator("..")
                .locator("..")
                .locator("..")
                .locator(".semi-select")
                .first
            )
            if not await dropdown.count():
                douyin_logger.error("[-] 未找到标签下拉框")
                return False
            douyin_logger.debug("[-] 找到标签下拉框，准备选择'购物车'")
            await dropdown.click()
            await page.wait_for_selector('[role="listbox"]', timeout=5000)
            await page.locator('[role="option"]:has-text("购物车")').click()
            douyin_logger.debug("[+] 成功选择'购物车'")

            await page.wait_for_selector('input[placeholder="粘贴商品链接"]', timeout=5000)
            input_field = page.locator('input[placeholder="粘贴商品链接"]')
            await input_field.fill(product_link)
            douyin_logger.debug(f"[+] 已输入商品链接: {product_link}")

            add_button = page.locator('span:has-text("添加链接")')
            button_class = await add_button.get_attribute("class")
            if "disable" in button_class:
                douyin_logger.error("[-] '添加链接'按钮不可用")
                return False
            await add_button.click()
            douyin_logger.debug("[+] 成功点击'添加链接'按钮")
            await page.wait_for_timeout(2000)
            error_modal = page.locator("text=未搜索到对应商品")
            if await error_modal.count():
                confirm_button = page.locator('button:has-text("确定")')
                await confirm_button.click()
                douyin_logger.error("[-] 商品链接无效")
                return False

            if not await self.handle_product_dialog(page, product_title):
                return False

            douyin_logger.debug("[+] 成功设置商品链接")
            return True
        except Exception as e:
            douyin_logger.error(f"[-] 设置商品链接时出错: {str(e)}")
            return False

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)

