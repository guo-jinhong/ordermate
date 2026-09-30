import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ResultList from './ResultList.vue'

describe('ResultList', () => {
  it.each([
    {
      kind: 'product' as const,
      payload: { kind: 'product' as const, items: [{ id: 1, name: '测试商品' }], context: {} },
      title: '商品结果',
      value: '测试商品',
    },
    {
      kind: 'cart' as const,
      payload: { kind: 'cart' as const, items: [{ cartId: 2, productName: '购物车商品' }] },
      title: '购物车结果',
      value: '购物车商品',
    },
    {
      kind: 'order' as const,
      payload: { kind: 'order' as const, items: [{ id: 3, orderNo: 'ORD-3' }] },
      title: '订单结果',
      value: 'ORD-3',
    },
  ])('dispatches the $kind branch', ({ payload, kind, title, value }) => {
    const wrapper = mount(ResultList, { props: { payload } })

    expect(wrapper.get(`[data-result-kind="${kind}"]`).text()).toContain(title)
    expect(wrapper.text()).toContain(value)
  })

  it('renders empty results and forwards the action prompt', async () => {
    const wrapper = mount(ResultList, {
      props: { payload: { kind: 'empty', emptyKind: 'order' } },
    })

    await wrapper.get('button').trigger('click')

    expect(wrapper.text()).toContain('暂时没有订单')
    expect(wrapper.emitted('prompt')).toEqual([[{
      prompt: '推荐一些商品',
      label: '去查看商品',
      authRequired: false,
    }]])
  })

  it('renders raw results and renders nothing for none', async () => {
    const wrapper = mount(ResultList, {
      props: { payload: { kind: 'raw', value: { custom: true } } },
    })
    expect(wrapper.text()).toContain('查看未识别数据')

    await wrapper.setProps({ payload: { kind: 'none' } })
    expect(wrapper.html()).toBe('<!--v-if-->')
  })
})
