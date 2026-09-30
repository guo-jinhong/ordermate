// 仅翻译内置演示目录的文案，未知品牌/型号保留原文。
const demoCopy: Record<string, string> = {
  'Wireless Headphones': '无线降噪耳机',
  'Smartphone X': '智能手机 X',
  'Laptop Pro 14': '专业笔记本电脑 14',
  'Cotton T-Shirt': '纯棉圆领 T 恤',
  'Running Sneakers': '轻量跑步鞋',
  'Ceramic Mug Set': '陶瓷马克杯套装',
  'Stainless Steel Kettle': '不锈钢电热水壶',
  'Spring Framework Guide': 'Spring 框架指南',
  'Yoga Mat': '防滑瑜伽垫',
  'Adjustable Dumbbells': '可调节哑铃',
  'Noise-cancelling over-ear headphones': '头戴式降噪耳机',
  '6.5-inch OLED, 128GB storage': '6.5 英寸 OLED 屏幕，128GB 存储',
  '14-inch, 16GB RAM, 512GB SSD': '14 英寸屏幕，16GB 内存，512GB 固态硬盘',
  'Unisex 100% cotton crew-neck tee': '男女同款，100% 纯棉圆领 T 恤',
  'Lightweight breathable running shoes': '轻量透气跑步鞋',
  'Set of 4 ceramic mugs, 350ml each': '4 件陶瓷马克杯套装，每杯 350ml',
  '1.7L electric kettle, fast boil': '1.7L 电热水壶，快速烧水',
  'Comprehensive Spring Boot 3 reference': 'Spring Boot 3 综合参考指南',
  '6mm non-slip yoga mat with carry strap': '6mm 防滑瑜伽垫，附便携绑带',
  'Pair of 2.5-25kg adjustable dumbbells': '一对 2.5–25kg 可调节哑铃',
}

export function customerCopy(text: string): string {
  return Object.entries(demoCopy).reduce(
    (result, [original, translation]) => result.replaceAll(original, translation), text,
  )
}

// 用户也可以直接输入页面上的中文名称；还原为业务目录名称以保持检索一致。
export function catalogQuery(text: string): string {
  return Object.entries(demoCopy).reduce(
    (result, [original, translation]) => result.replaceAll(translation, original), text,
  )
}
