import { expect, test } from '@playwright/test'

test('隔离手机测试：确认过期后禁用按钮且不会发送写请求', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.clock.install({ time: new Date('2026-10-02T00:00:00Z') })
  await page.addInitScript(() => {
    sessionStorage.setItem('ordermate_token', 'isolated-browser-test')
    sessionStorage.setItem('ordermate_username', '测试用户')
  })
  let confirmations = 0
  await page.route('**/auth/session', route => route.fulfill({ json: { authenticated: true, username: '测试用户' } }))
  await page.route('**/confirm', route => { confirmations += 1; return route.fulfill({ json: { status: 'executed', message: '已执行', data: [] } }) })
  await page.route('**/chat/stream', route => route.fulfill({
    contentType: 'text/event-stream', body: `event: result\ndata: ${JSON.stringify({
      answer: '请确认清空购物车。', data: null, tool_calls: [{ name: 'clear_cart', arguments: {}, outcome: 'confirmation_required' }],
      confirmation: { token: 'expiry-test', action: 'clear_cart', description: '清空当前购物车', arguments: {}, expires_at: '2026-10-02T00:01:00Z' },
    })}\n\n`,
  }))
  await page.goto('/')
  await page.getByPlaceholder('描述你想查找或处理的内容…').fill('清空购物车')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const card = page.locator('.confirmation-card')
  await expect(card).toContainText('秒内确认')
  await expect(card.getByRole('button', { name: '确认清空购物车', exact: true })).toBeEnabled()
  await page.clock.fastForward(61000)
  await expect(card).toContainText('本次确认已过期')
  await expect(card.getByRole('button', { name: '确认清空购物车', exact: true })).toBeDisabled()
  expect(confirmations).toBe(0)
})

test('Vue -> Agent -> Java -> MySQL 商品检索链路', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('button', { name: '新建会话' })).toBeVisible()
  await page.getByPlaceholder('描述你想查找或处理的内容…').fill('搜索 Smartphone X')
  await page.getByRole('button', { name: '发送' }).click()

  await expect(page.locator('.product-card').filter({ hasText: '智能手机 X' }).last()).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('.product-card').last()).toContainText('¥2,999')
  await page.getByPlaceholder('描述你想查找或处理的内容…').fill('搜索 Spring Framework Guide')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const book = page.locator('.product-card').filter({ hasText: 'Spring 框架指南' }).last()
  await expect(book).toBeVisible({ timeout: 20_000 })
  const detailRequest = page.waitForRequest(request => request.url().endsWith('/chat/stream') && request.method() === 'POST')
  await book.getByRole('button', { name: 'Spring 框架指南', exact: true }).click()
  expect((await detailRequest).postDataJSON().message).toBe('查看商品 8 的详情')
  await expect(page.locator('.product-card').filter({ hasText: 'Spring 框架指南' })).toHaveCount(2, { timeout: 20_000 })
})

test('隔离浏览器测试：旧商品卡、商品ID和购物车项ID始终对应', async ({ page }) => {
  const requests: string[] = []
  let bookQuantity = 0
  await page.addInitScript(() => {
    sessionStorage.setItem('ordermate_token', 'isolated-browser-test')
    sessionStorage.setItem('ordermate_username', '测试用户')
  })
  await page.route('**/auth/session', route => route.fulfill({ json: { authenticated: true, username: '测试用户' } }))
  await page.route('**/chat/stream', async route => {
    const message = route.request().postDataJSON().message as string
    requests.push(message)
    let name = 'search_products'
    let answer = '业务结果已核对'
    let args: Record<string, number | string> = { keyword: '' }
    let data: unknown = [{ id: 2, name: 'Smartphone X', price: 2999, stock: 30 }, { id: 8, name: 'Spring Framework Guide', price: 99, stock: 80 }]
    if (message.includes('加入购物车')) { name = 'add_to_cart'; args = { product_id: 8, quantity: 1 }; data = null; bookQuantity += 1; answer = `本次为您加入「Spring Framework Guide」1件，购物车中这件商品现在共有 ${bookQuantity} 件。` }
    else if (message.includes('的详情')) { name = 'get_product_detail'; args = { product_id: 8 }; data = { id: 8, name: 'Spring Framework Guide', price: 99, stock: 80 } }
    else if (message.includes('数量改为')) { name = 'update_cart'; args = { cart_id: 71, quantity: 2 }; data = null }
    else if (message.includes('移除')) { name = 'remove_from_cart'; args = { cart_id: 71 }; data = null }
    else if (message.includes('购物车')) {
      name = 'get_cart'; args = {}; data = [{ cartId: 71, productId: 8, productName: 'Spring Framework Guide', price: 99, quantity: 1 }, { cartId: 72, productId: 2, productName: 'Smartphone X', price: 2999, quantity: 1 }]
    }
    await route.fulfill({ contentType: 'text/event-stream', body: `event: result\ndata: ${JSON.stringify({ answer, tool_calls: [{ name, arguments: args, outcome: 'success' }], data, confirmation: null, reference: null })}\n\n` })
  })
  await page.goto('/')
  await expect(page.getByText('测试用户', { exact: true })).toBeVisible()
  await page.getByPlaceholder('描述你想查找或处理的内容…').fill('推荐商品')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const oldBook = page.locator('.product-card').filter({ hasText: 'Spring 框架指南' }).first()
  await oldBook.getByRole('button', { name: '加入购物车', exact: true }).click()
  await expect.poll(() => requests.at(-1)).toBe('将商品 8 加入购物车，数量 1 件')
  await expect(page.locator('.answer').filter({ hasText: '现在共有 1 件' })).toBeVisible()
  await expect(oldBook.getByRole('button', { name: '加入购物车', exact: true })).toBeEnabled()
  await oldBook.getByRole('button', { name: '加入购物车', exact: true }).click()
  await expect(page.locator('.answer').filter({ hasText: '现在共有 2 件' })).toBeVisible()
  await expect(page.locator('.reference')).toHaveCount(0)

  await expect(oldBook.getByRole('button', { name: 'Spring 框架指南', exact: true })).toBeEnabled()
  await oldBook.getByRole('button', { name: 'Spring 框架指南', exact: true }).click()
  await expect.poll(() => requests.at(-1)).toBe('查看商品 8 的详情')
  await expect(page.locator('.product-card')).toHaveCount(3)
  await page.getByRole('button', { name: '查看购物车', exact: true }).click()
  const cartBook = page.locator('.cart-card').filter({ hasText: 'Spring 框架指南' })
  await expect(cartBook).toBeVisible()
  await cartBook.getByRole('button', { name: '增加Spring Framework Guide的数量' }).click()
  await expect.poll(() => requests.at(-1)).toBe('将购物车项 71 的数量改为 2 件')
  await page.locator('[data-result-kind=cart]').getByRole('button', { name: '管理', exact: true }).click()
  await expect(cartBook.getByRole('button', { name: '移除', exact: true })).toBeEnabled()
  await cartBook.getByRole('button', { name: '移除', exact: true }).click()
  await expect.poll(() => requests.at(-1)).toBe('移除购物车项 71')
  expect(requests).toEqual(['推荐商品', '将商品 8 加入购物车，数量 1 件', '将商品 8 加入购物车，数量 1 件', '查看商品 8 的详情', '查看我的购物车', '将购物车项 71 的数量改为 2 件', '移除购物车项 71'])
})


test('隔离手机测试：普通移除直接执行，清空购物车确认绑定原消息', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.addInitScript(() => {
    sessionStorage.setItem('ordermate_token', 'isolated-mobile-test')
    sessionStorage.setItem('ordermate_username', '测试用户')
  })
  await page.route('**/auth/session', route => route.fulfill({ json: { authenticated: true, username: '测试用户' } }))
  let removed = false
  let cleared = false
  const book = { cartId: 71, productId: 8, productName: 'Spring Framework Guide', quantity: 3, price: 99 }
  const phone = { cartId: 72, productId: 2, productName: 'Smartphone X', quantity: 1, price: 2999 }
  await page.route('**/chat/stream', async route => {
    const message = route.request().postDataJSON().message as string
    const removal = message === '移除购物车项 71'
    const clear = message === '清空购物车'
    if (removal) removed = true
    const result = {
      answer: clear ? '请确认清空购物车，确认后再执行。' : removal ? '已从购物车移除「Spring Framework Guide」。' : '已核对购物车。',
      tool_calls: [{ name: clear ? 'clear_cart' : removal ? 'remove_from_cart' : 'get_cart', arguments: removal ? { cart_id: 71 } : {}, outcome: clear ? 'confirmation_required' : 'success' }],
      confirmation: clear ? { token: 'clear-token', action: 'clear_cart', description: '清空购物车', arguments: {} } : null,
      data: clear ? null : cleared ? [] : removed ? [phone] : [book, phone], reference: null,
    }
    await route.fulfill({ contentType: 'text/event-stream', body: `event: result\ndata: ${JSON.stringify(result)}\n\n` })
  })
  const confirmations: string[] = []
  await page.route('**/confirm', async route => {
    confirmations.push(route.request().postDataJSON().confirmation_token)
    cleared = true
    await route.fulfill({ json: { status: 'executed', message: '购物车已清空。', data: [] } })
  })
  await page.goto('/')
  const send = async (text: string) => {
    await page.getByPlaceholder('描述你想查找或处理的内容…').fill(text)
    await page.getByRole('button', { name: '发送', exact: true }).click()
  }
  await send('查看我的购物车')
  await page.locator('.cart-card').filter({ hasText: 'Spring 框架指南' }).getByRole('button', { name: '移除', exact: true }).click()
  await expect(page.locator('.message').last().locator('.cart-card')).toHaveCount(1)
  await expect(page.locator('.message').last()).toContainText('智能手机 X')
  await expect(page.locator('.confirmation-card')).toHaveCount(0)
  expect(confirmations).toEqual([])
  await send('清空购物车')
  const confirmation = page.locator('.confirmation-card')
  await expect(confirmation.getByRole('button', { name: '确认清空购物车', exact: true })).toBeEnabled()
  expect(cleared).toBe(false)
  await send('查看我的购物车')
  await expect(page.locator('.message').last().locator('.cart-card')).toHaveCount(1)
  await confirmation.getByRole('button', { name: '确认清空购物车', exact: true }).click()
  await expect(confirmation).toContainText('购物车已清空')
  expect(confirmations).toEqual(['clear-token'])
  await send('查看我的购物车')
  await expect(page.locator('.message').last().locator('.cart-card')).toHaveCount(0)
  await expect(page.locator('.message').last()).toContainText('购物车还是空的')
})
