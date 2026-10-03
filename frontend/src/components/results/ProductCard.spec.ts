import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ProductCard from './ProductCard.vue'

describe('ProductCard', () => {
  it('binds translated book cards to their ID for both title and detail actions', async () => {
    const wrapper = mount(ProductCard, {
      props: { product: { id: 8, name: 'Spring Framework Guide', stock: 80 }, context: {} },
    })
    await wrapper.get('button.product-title').trigger('click')
    await wrapper.findAll('footer button')[0]!.trigger('click')
    expect(wrapper.text()).toContain('Spring 框架指南')
    for (const [action] of wrapper.emitted('prompt') || []) {
      expect(action).toMatchObject({ prompt: '查看商品 8 的详情', displayPrompt: '查看「Spring Framework Guide」的商品详情' })
    }
  })
  it('renders facts and at most three matching reasons', () => {
    const wrapper = mount(ProductCard, {
      props: {
        product: { id: 8, name: '测试手机', price: 2999, stock: 120, status: 1, categoryId: 101 },
        context: { keyword: '手机', min_price: 1000, max_price: 3000, in_stock: true },
      },
    })

    expect(wrapper.text()).toContain('测试手机')
    expect(wrapper.text()).toContain('¥2,999')
    expect(wrapper.text()).toContain('有货')
    expect(wrapper.text()).toContain('有货，可加入购物车')
    expect(wrapper.text()).not.toContain('最多可购买')
    expect(wrapper.text()).not.toContain('库存')
    expect(wrapper.text()).not.toContain('限购')
    expect(wrapper.text()).not.toContain('分类')
    expect(wrapper.text()).not.toContain('#101')
    expect(wrapper.findAll('.match li')).toHaveLength(3)
  })

  it('degrades missing fields and disables unavailable actions', () => {
    const wrapper = mount(ProductCard, {
      props: { product: { status: 0 }, context: {} },
    })

    expect(wrapper.text()).toContain('商品名称暂未显示')
    expect(wrapper.text()).toContain('价格待确认')
    expect(wrapper.text()).toContain('已下架')
    expect(wrapper.findAll('button').every((button) => button.attributes('disabled') !== undefined)).toBe(true)
  })

  it.each([
    [{ stock: 0 }, '暂时缺货'],
    [{ stock: null }, '购买状态待确认'],
    [{ stock: 1.5 }, '购买状态待确认'],
    [{ stock: 10, status: 0 }, '已下架'],
  ])('does not present a purchase quantity for unavailable goods: %j', (product, label) => {
    const wrapper = mount(ProductCard, { props: { product: { id: 8, ...product }, context: {} } })
    expect(wrapper.text()).toContain(label)
    expect(wrapper.text()).not.toContain('当前最多可购买')
    expect(wrapper.get('button.primary').attributes('disabled')).toBeDefined()
  })

  it('emits a login-required cart intent', async () => {
    const wrapper = mount(ProductCard, {
      props: { product: { id: 8, name: '测试手机', price: 2999, stock: 10 }, context: {} },
    })

    await wrapper.get('button.primary').trigger('click')

    expect(wrapper.emitted('prompt')?.[0]?.[0]).toEqual({
      prompt: '将商品 8 加入购物车，数量 1 件',
      displayPrompt: '将「测试手机」加入购物车，数量 1 件',
      label: '加入个人购物车',
      authRequired: true,
    })
  })
})
