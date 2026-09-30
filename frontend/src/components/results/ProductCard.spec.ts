import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ProductCard from './ProductCard.vue'

describe('ProductCard', () => {
  it('renders facts and at most three matching reasons', () => {
    const wrapper = mount(ProductCard, {
      props: {
        product: { id: 8, name: '测试手机', price: 2999, stock: 10, status: 1, categoryId: 101 },
        context: { keyword: '手机', min_price: 1000, max_price: 3000, in_stock: true },
      },
    })

    expect(wrapper.text()).toContain('测试手机')
    expect(wrapper.text()).toContain('¥2,999')
    expect(wrapper.text()).toContain('有货')
    expect(wrapper.text()).not.toContain('分类')
    expect(wrapper.text()).not.toContain('#101')
    expect(wrapper.findAll('.match li')).toHaveLength(3)
  })

  it('degrades missing fields and disables unavailable actions', () => {
    const wrapper = mount(ProductCard, {
      props: { product: { status: 0 }, context: {} },
    })

    expect(wrapper.text()).toContain('未命名商品')
    expect(wrapper.text()).toContain('价格待确认')
    expect(wrapper.text()).toContain('已下架')
    expect(wrapper.findAll('button').every((button) => button.attributes('disabled') !== undefined)).toBe(true)
  })

  it('emits a login-required cart intent', async () => {
    const wrapper = mount(ProductCard, {
      props: { product: { id: 8, name: '测试手机', price: 2999, stock: 10 }, context: {} },
    })

    await wrapper.findAll('button')[1]?.trigger('click')

    expect(wrapper.emitted('prompt')?.[0]?.[0]).toEqual({
      prompt: '将「测试手机」加入购物车，数量 1 件',
      label: '加入个人购物车',
      authRequired: true,
    })
  })
})
