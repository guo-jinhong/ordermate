import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import EmptyResult from './EmptyResult.vue'

describe('EmptyResult', () => {
  it('renders the copy for each result kind', () => {
    const product = mount(EmptyResult, { props: { kind: 'product' } })
    const cart = mount(EmptyResult, { props: { kind: 'cart' } })
    const order = mount(EmptyResult, { props: { kind: 'order' } })

    expect(product.text()).toContain('没有找到匹配商品')
    expect(cart.text()).toContain('购物车还是空的')
    expect(order.text()).toContain('暂时没有订单')
  })

  it('emits a usable next-step prompt', async () => {
    const wrapper = mount(EmptyResult, { props: { kind: 'cart' } })

    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('prompt')).toEqual([[{
      prompt: '推荐一些有货的商品',
      label: '去搜索商品',
      authRequired: false,
    }]])
  })
})
