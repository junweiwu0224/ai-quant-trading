import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AsyncState from './AsyncState.vue'
import BaseButton from './BaseButton.vue'
import BaseCard from './BaseCard.vue'
import BaseTabs from './BaseTabs.vue'
import BaseTag from './BaseTag.vue'

describe('AsyncState', () => {
  it('announces errors assertively and success politely', () => {
    const error = mount(AsyncState, { props: { state: 'error', message: '加载失败' } })
    expect(error.attributes('role')).toBe('alert')
    expect(error.attributes('aria-live')).toBe('assertive')

    const success = mount(AsyncState, { props: { state: 'success', message: '保存完成' } })
    expect(success.attributes('role')).toBe('status')
    expect(success.attributes('aria-live')).toBe('polite')
  })
})

describe('BaseButton', () => {
  it('renders with default props', () => {
    const wrapper = mount(BaseButton, {
      slots: {
        default: 'Click me'
      }
    })
    expect(wrapper.text()).toBe('Click me')
    expect(wrapper.classes()).toContain('base-button')
    expect(wrapper.classes()).toContain('base-button--primary')
    expect(wrapper.classes()).toContain('base-button--md')
  })

  it('renders different variants', () => {
    const variants = ['primary', 'secondary', 'ghost', 'danger'] as const
    variants.forEach(variant => {
      const wrapper = mount(BaseButton, {
        props: { variant }
      })
      expect(wrapper.classes()).toContain(`base-button--${variant}`)
    })
  })

  it('renders different sizes', () => {
    const sizes = ['sm', 'md', 'lg'] as const
    sizes.forEach(size => {
      const wrapper = mount(BaseButton, {
        props: { size }
      })
      expect(wrapper.classes()).toContain(`base-button--${size}`)
    })
  })

  it('emits click event when clicked', async () => {
    const wrapper = mount(BaseButton)
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')?.[0]).toBeTruthy()
  })

  it('does not emit click when disabled', async () => {
    const wrapper = mount(BaseButton, {
      props: { disabled: true }
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeFalsy()
  })

  it('shows loading spinner when loading', () => {
    const wrapper = mount(BaseButton, {
      props: { loading: true }
    })
    expect(wrapper.find('.base-button__spinner').exists()).toBe(true)
    expect(wrapper.classes()).toContain('base-button--loading')
  })
})

describe('BaseCard', () => {
  it('renders with default props', () => {
    const wrapper = mount(BaseCard, {
      slots: {
        default: 'Card content'
      }
    })
    expect(wrapper.text()).toBe('Card content')
    expect(wrapper.classes()).toContain('base-card')
    expect(wrapper.classes()).toContain('base-card--padding-md')
  })

  it('renders different padding sizes', () => {
    const paddings = ['sm', 'md', 'lg'] as const
    paddings.forEach(padding => {
      const wrapper = mount(BaseCard, {
        props: { padding }
      })
      expect(wrapper.classes()).toContain(`base-card--padding-${padding}`)
    })
  })

  it('applies elevated class when prop is true', () => {
    const wrapper = mount(BaseCard, {
      props: { elevated: true }
    })
    expect(wrapper.classes()).toContain('base-card--elevated')
  })

  it('applies bordered class by default', () => {
    const wrapper = mount(BaseCard)
    expect(wrapper.classes()).toContain('base-card--bordered')
  })

  it('applies hoverable class when prop is true', () => {
    const wrapper = mount(BaseCard, {
      props: { hoverable: true }
    })
    expect(wrapper.classes()).toContain('base-card--hoverable')
  })
})

describe('BaseTabs', () => {
  const tabs = [
    { id: 'tab1', label: 'Tab 1' },
    { id: 'tab2', label: 'Tab 2' },
    { id: 'tab3', label: 'Tab 3', badge: 5 }
  ]

  it('renders all tabs', () => {
    const wrapper = mount(BaseTabs, {
      props: { tabs, modelValue: 'tab1' }
    })
    const tabButtons = wrapper.findAll('.base-tabs__tab')
    expect(tabButtons).toHaveLength(3)
  })

  it('marks active tab', () => {
    const wrapper = mount(BaseTabs, {
      props: { tabs, modelValue: 'tab2' }
    })
    const tabButtons = wrapper.findAll('.base-tabs__tab')
    expect(tabButtons[1].classes()).toContain('base-tabs__tab--active')
  })

  it('emits update:modelValue when tab clicked', async () => {
    const wrapper = mount(BaseTabs, {
      props: { tabs, modelValue: 'tab1' }
    })
    const secondTab = wrapper.findAll('.base-tabs__tab')[1]
    await secondTab.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['tab2'])
  })

  it('renders badge when provided', () => {
    const wrapper = mount(BaseTabs, {
      props: { tabs, modelValue: 'tab1' }
    })
    const badge = wrapper.find('.base-tabs__badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('5')
  })

  it('disables tab when disabled prop is true', () => {
    const disabledTabs = [
      ...tabs,
      { id: 'tab4', label: 'Disabled', disabled: true }
    ]
    const wrapper = mount(BaseTabs, {
      props: { tabs: disabledTabs, modelValue: 'tab1' }
    })
    const disabledTab = wrapper.findAll('.base-tabs__tab')[3]
    expect(disabledTab.classes()).toContain('base-tabs__tab--disabled')
  })
})

describe('BaseTag', () => {
  it('renders with default props', () => {
    const wrapper = mount(BaseTag, {
      slots: {
        default: 'Tag text'
      }
    })
    expect(wrapper.text()).toBe('Tag text')
    expect(wrapper.classes()).toContain('base-tag')
    expect(wrapper.classes()).toContain('base-tag--default')
    expect(wrapper.classes()).toContain('base-tag--md')
  })

  it('renders different variants', () => {
    const variants = ['default', 'success', 'warning', 'danger', 'info', 'up', 'down'] as const
    variants.forEach(variant => {
      const wrapper = mount(BaseTag, {
        props: { variant }
      })
      expect(wrapper.classes()).toContain(`base-tag--${variant}`)
    })
  })

  it('renders different sizes', () => {
    const sizes = ['sm', 'md', 'lg'] as const
    sizes.forEach(size => {
      const wrapper = mount(BaseTag, {
        props: { size }
      })
      expect(wrapper.classes()).toContain(`base-tag--${size}`)
    })
  })

  it('shows close button when closable', () => {
    const wrapper = mount(BaseTag, {
      props: { closable: true }
    })
    expect(wrapper.find('.base-tag__close').exists()).toBe(true)
  })

  it('emits close event when close button clicked', async () => {
    const wrapper = mount(BaseTag, {
      props: { closable: true }
    })
    const closeButton = wrapper.find('.base-tag__close')
    await closeButton.trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('does not show close button by default', () => {
    const wrapper = mount(BaseTag)
    expect(wrapper.find('.base-tag__close').exists()).toBe(false)
  })
})
