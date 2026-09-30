import { expect, test } from '@playwright/test'

test('Vue -> Agent -> Java -> MySQL 商品检索链路', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByText(/Agent (在线|降级)/)).toBeVisible()
  await page.getByPlaceholder('描述你想查找或处理的内容…').fill('搜索 Smartphone X')
  await page.getByRole('button', { name: '发送' }).click()

  await expect(page.getByText('Smartphone X').last()).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText(/2999|OLED|库存/).last()).toBeVisible()
})
