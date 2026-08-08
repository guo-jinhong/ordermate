-- ============================================================
-- 电商客服 Agent 知识库增强脚本
-- 数据库: ecommerce_db
-- 用途: 仅更新 knowledge 表，不修改商品、订单、购物车等业务数据
-- ============================================================

USE ecommerce_db;

CREATE TABLE IF NOT EXISTS knowledge (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '知识ID',
    category VARCHAR(64) NOT NULL COMMENT '分类',
    title VARCHAR(200) NOT NULL COMMENT '知识标题',
    content TEXT NOT NULL COMMENT '知识内容',
    keywords VARCHAR(500) DEFAULT NULL COMMENT '关键词，用于搜索',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_category (category),
    FULLTEXT INDEX ft_keywords (keywords, title)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库表';

START TRANSACTION;

DELETE FROM knowledge;
ALTER TABLE knowledge AUTO_INCREMENT = 1;

INSERT INTO knowledge (category, title, content, keywords) VALUES
('refund', '7天无理由退货总则', '自签收次日起7天内，商品未影响二次销售、配件赠品齐全、包装完整的，可申请7天无理由退货。定制商品、虚拟商品、已拆封的一次性卫生用品、明确标注不支持无理由退货的商品除外。', '退款 退货 7天 无理由 二次销售 包装 配件 赠品');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('refund', '非质量问题退货运费', '非质量问题申请7天无理由退货时，寄回运费由用户承担。平台活动页或商品页明确承诺退货包运费的，以承诺规则为准。到付件可能被仓库拒收。', '退款 退货 运费 非质量问题 到付 包运费');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('refund', '质量问题退货运费', '商品存在质量问题、错发、漏发、运输破损且经客服或售后审核通过的，退货运费由平台承担。用户需提供照片、视频、检测报告或物流破损证明等必要凭证。', '质量问题 退货 运费 错发 漏发 破损 凭证');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('refund', '退款到账时间', '退货入库并验收通过后，退款通常在1-3个工作日内原路退回；银行卡渠道可能需要3-7个工作日。节假日、银行清算延迟、风控复核会延长到账时间。', '退款 到账 原路退回 银行卡 工作日 清算 风控');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('refund', '部分退款规则', '订单中仅部分商品退货时，仅退回对应商品实付金额。整单优惠、满减、优惠券、积分抵扣会按商品实付占比分摊后计算退款金额。运费是否退回以退货原因和包邮条件为准。', '部分退款 实付金额 满减 优惠券 积分 运费 分摊');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('refund', '拒绝退款边界', '商品已超过售后期、人为损坏、缺少关键配件、影响二次销售、无法提供必要凭证或售后审核未通过时，平台可拒绝退款申请，并说明原因。', '拒绝退款 售后期 人为损坏 缺配件 二次销售 审核');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('refund', '已使用优惠券退款', '使用优惠券的订单发生退款时，若整单全部退款且优惠券仍在有效期内，优惠券可退回；部分退款或优惠券已过期时，优惠券通常不退回，仅退还分摊后的现金实付金额。', '优惠券 退款 退回 过期 部分退款 实付');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('refund', '积分抵扣退款', '订单使用积分抵扣后发生退款，现金部分原路退回，积分按退款商品分摊比例退回账户。已过有效期的积分是否退回以活动规则为准。', '积分 退款 抵扣 原路退回 有效期');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('refund', '退货验收不通过', '退货商品入库后如发现缺件、损坏、污渍、序列号不一致、非本平台售出商品等情况，仓库会标记验收异常，客服需联系用户补充说明，退款会暂停处理。', '退货 验收 异常 缺件 损坏 序列号 暂停退款');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('refund', '退款申请撤销', '用户可在退货寄出前撤销退款申请。退货已寄出或仓库已入库时，是否能撤销需由客服核实物流和仓库状态。', '撤销退款 退货寄出 仓库 入库');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('return_exchange', '换货申请条件', '自签收次日起7天内，商品存在质量问题、尺码不合适、错发漏发等情况可申请换货。换货商品需库存充足，且原商品、配件、赠品、发票需按要求寄回。', '换货 条件 质量问题 尺码 错发 漏发 库存');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('return_exchange', '换货流程', '换货流程为：提交申请、填写原因、上传凭证、客服审核、寄回商品、仓库验收、发出新商品。审核和仓库验收任一环节不通过，换货可能被拒绝。', '换货 流程 申请 审核 寄回 验收 发货');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('return_exchange', '换货运费规则', '质量问题、错发漏发导致的换货，平台承担往返运费；非质量问题换货，寄回运费由用户承担，新商品寄出运费按活动或会员权益判断。', '换货 运费 往返运费 非质量问题 质量问题');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('return_exchange', '无库存换货处理', '用户申请换货但同款商品无库存时，可选择等待补货、换同价可售商品、补差价换其他商品，或改为退款。', '换货 无库存 补货 同价 补差价 退款');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('return_exchange', '换货商品保价', '换货不重新计算原订单活动价，原则上按原订单成交价处理。若用户主动更换不同商品或不同规格，需按当前规则补差价或退差价。', '换货 保价 活动价 成交价 补差价 退差价');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('return_exchange', '特殊品类换货', '耳机、牙刷、贴身衣物等涉及卫生安全的商品，非质量问题且已拆封使用后通常不支持换货。商品页另有承诺的按商品页规则执行。', '特殊品类 换货 耳机 牙刷 贴身衣物 拆封 卫生');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('cancel_order', '待支付订单取消', '待支付订单可由用户自行取消，取消后库存释放，优惠券和积分按规则返还。若订单超过系统支付时限未支付，也会自动关闭。', '取消订单 待支付 自动关闭 库存 优惠券 积分');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('cancel_order', '已支付未发货取消', '已支付但未发货订单需要提交取消申请。若仓库尚未拣货或出库，可取消并退款；若已进入拣货、打包或出库流程，可能无法拦截，需按退货流程处理。', '取消订单 已支付 未发货 仓库 拣货 出库 拦截');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('cancel_order', '已发货订单取消', '订单已发货后通常不能直接取消。用户可拒收或签收后申请退货。拒收产生的运费责任按订单原因、商品问题和活动规则判断。', '取消订单 已发货 拒收 签收 退货 运费');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('cancel_order', '已完成订单取消', '已完成订单不能取消，只能按售后规则申请退货、换货、维修或投诉处理。客服不能直接把已完成订单改为取消状态。', '取消订单 已完成 售后 退货 换货 维修');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('cancel_order', '取消失败处理', '取消失败时应告知用户失败原因，例如订单状态不允许、仓库已出库、支付状态异常或系统正在处理。不得承诺一定取消成功。', '取消失败 订单状态 出库 支付异常 承诺');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('cancel_order', '重复取消防护', '同一订单在短时间内重复提交取消申请时，应提示用户已有申请正在处理，避免重复操作和重复退款。', '重复取消 防重复 取消申请 重复退款');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('payment', '支付方式', '平台支持支付宝、微信支付、银联云闪付、银行卡快捷支付、信用卡和花呗分期。实际可用方式以结算页展示为准。', '支付方式 支付宝 微信 银联 银行卡 信用卡 分期');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('payment', '支付失败处理', '支付失败时可建议用户检查余额、银行卡限额、网络状态、支付密码、风控短信或更换支付方式。若银行已扣款但订单未支付成功，应等待系统对账或联系客服处理。', '支付失败 扣款 未支付 对账 限额 风控');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('payment', '重复支付处理', '同一订单重复支付时，系统通常会自动原路退回多付金额。若24小时内未退回，需提供订单号、支付流水号和扣款截图给客服核查。', '重复支付 多付 退款 支付流水 扣款截图');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('payment', '支付超时关闭', '待支付订单超过配置时间未完成支付会自动关闭。订单关闭后不能继续支付，用户需重新下单，价格、库存、优惠以重新下单时为准。', '支付超时 订单关闭 重新下单 库存 优惠');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('payment', '分期付款规则', '分期付款是否可用取决于支付渠道、商品类型、订单金额和用户账户状态。分期手续费、期数和还款规则以支付渠道页面展示为准。', '分期付款 手续费 期数 支付渠道 还款');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('payment', '支付安全边界', '客服不能索要用户支付密码、银行卡完整卡号、短信验证码、身份证完整照片或远程控制用户设备。涉及资金异常时只引导用户通过官方渠道处理。', '支付安全 密码 验证码 银行卡 资金异常 官方渠道');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('coupon', '优惠券使用规则', '优惠券需满足使用门槛、适用品类、适用店铺、有效期和用户身份限制。每笔订单默认仅可使用一张优惠券，是否可叠加以活动页说明为准。', '优惠券 使用门槛 有效期 品类 店铺 叠加');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('coupon', '优惠券不可用原因', '优惠券不可用常见原因包括未达到满减门槛、商品不在适用范围、优惠券过期、账号不符合条件、订单含特殊商品或已使用其他互斥优惠。', '优惠券 不可用 门槛 过期 互斥 特殊商品');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('coupon', '优惠券退款返还', '整单退款时，未过期优惠券通常退回；部分退款、订单已完成后退款或优惠券过期时，优惠券可能不退回。具体以活动规则为准。', '优惠券 退款 退回 部分退款 过期 活动规则');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('coupon', '满减活动规则', '满减金额按商品实付前的活动规则计算。取消、退货导致订单不再满足满减门槛时，退款金额需扣除已享受优惠的分摊部分。', '满减 活动 退款 分摊 门槛 优惠');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('coupon', '价格保护规则', '商品支持价保时，用户可在价保期内申请补差。秒杀、清仓、赠品、优惠券差异、会员专享价、跨店满减等特殊活动通常不参与价保。', '价保 保价 补差 秒杀 清仓 会员价 跨店满减');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('shipping', '发货时效', '现货商品通常下单后24小时内发货；大促、预售、缺货、偏远地区、不可抗力或人工审核订单可能延迟发货。具体以订单页预计发货时间为准。', '发货 时效 24小时 预售 缺货 大促 延迟');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('shipping', '配送时效', '一线和主要城市通常1-3天送达，普通地区3-5天，偏远地区3-7天或更久。物流时效受天气、交通、节假日和承运商影响。', '配送 时效 一线城市 偏远地区 物流 天气 节假日');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('shipping', '运费规则', '单笔订单满99元免基础运费，不足99元收取10元基础运费。超重、超大件、偏远地区、冷链或特殊配送可能产生额外运费。', '运费 包邮 满99 超重 超大件 偏远 冷链');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('shipping', '物流异常处理', '物流长时间不更新、派送失败、疑似丢件或签收异常时，客服应先核实物流单号和承运商记录，再发起物流工单。未核实前不得直接承诺补发或退款。', '物流异常 不更新 派送失败 丢件 签收 工单');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('shipping', '包裹破损处理', '用户签收时发现外包装严重破损，应建议当场拍照、拒收或让快递员备注异常。已签收后发现破损，需在24小时内提供外包装和商品照片。', '包裹破损 拒收 拍照 签收 快递备注 24小时');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('shipping', '地址修改规则', '订单未发货且未进入仓库作业时可申请修改收货地址。订单已出库或已发货后通常不能修改地址，可尝试联系承运商改派，结果不保证。', '修改地址 未发货 仓库 出库 改派 承运商');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('shipping', '拆单发货规则', '订单包含多个仓库、预售商品、缺货商品或大件商品时，可能拆单发货。拆单不影响订单总金额，用户可分别查看每个包裹物流。', '拆单 发货 多仓 预售 缺货 包裹物流');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('shipping', '拒收处理规则', '用户拒收后，包裹需退回仓库并完成入库验收，退款才会处理。非质量问题拒收产生的运费可能由用户承担。', '拒收 退回仓库 入库验收 退款 运费');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('invoice', '发票类型', '平台支持电子普通发票和增值税专用发票。可开票类型、税率和开票主体以订单商品、商家资质和结算页展示为准。', '发票 普票 专票 税率 开票主体');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('invoice', '发票申请时限', '订单支付成功后可申请发票。已退款、已取消或超过平台规定开票期限的订单，可能无法开票。', '发票 申请 支付成功 已退款 已取消 开票期限');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('invoice', '发票抬头修改', '发票开具前可修改抬头和税号；发票已开具后如需修改，需先作废或红冲原发票，能否重开取决于发票状态和财务规则。', '发票 抬头 税号 修改 作废 红冲 重开');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('invoice', '发票与退款', '已开发票订单发生退款时，用户需按要求退回纸质发票或配合电子发票冲红。未完成发票处理可能影响退款进度。', '发票 退款 纸质发票 电子发票 冲红');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('invoice', '企业发票信息', '企业发票需提供准确的公司名称、纳税人识别号、地址电话、开户行及账号等信息。信息错误导致无法抵扣或报销的，由用户自行承担。', '企业发票 纳税人识别号 开户行 报销 抵扣');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('membership', '会员等级规则', '会员等级按近12个月有效消费金额计算，退款、取消、虚假交易和风控订单不计入有效消费。等级更新可能存在系统延迟。', '会员 等级 有效消费 退款 风控 延迟');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('membership', '积分获取规则', '用户每实际支付1元可获得1积分，运费、优惠券抵扣、退款金额、虚拟赠品和违规订单不产生积分。积分到账可能在订单完成后生效。', '积分 获取 实付 运费 优惠券 订单完成');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('membership', '积分使用规则', '积分可按100积分抵1元使用，是否可与优惠券、满减、会员价叠加，以结算页展示为准。积分抵扣不能兑换现金。', '积分 使用 抵现 结算 叠加 现金');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('membership', '积分有效期', '积分有效期通常为12个月，过期未使用会自动失效。已失效积分一般不补发，平台系统故障导致的异常除外。', '积分 有效期 过期 失效 补发');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('membership', '会员权益边界', '会员折扣、免运费、优先客服、生日礼包等权益可能受商品、地区、活动和账号状态限制。权益不得转让、出售或折现。', '会员权益 折扣 免运费 优先客服 生日礼包 转让');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('warranty', '质保范围', '商品在质保期内出现非人为性能故障，可按品牌或平台规则申请维修、换货或退货。人为损坏、进水、私拆、改装、外观磨损通常不属于质保范围。', '质保 保修 维修 人为损坏 进水 私拆 改装');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('warranty', '质保凭证', '申请质保需提供订单号、商品照片或视频、故障描述、序列号、检测报告等材料。资料不完整时，售后可能要求补充后再审核。', '质保 凭证 订单号 序列号 检测报告 审核');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('warranty', '手机电脑售后', '手机、电脑等数码商品如出现质量问题，可能需要品牌授权售后检测。平台依据检测结果确认维修、换货、退货或拒绝售后。', '手机 电脑 数码 检测 授权售后 维修');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('warranty', '耳机类售后', '耳机类商品涉及卫生和佩戴属性，非质量问题拆封后通常不支持退换。质量问题需提供故障视频、左右耳序列号或检测凭证。', '耳机 售后 拆封 卫生 故障视频 序列号');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('warranty', '服饰鞋靴售后', '服饰鞋靴需保持吊牌、包装、配件完整且无穿着、洗涤、污渍、异味、破损。尺码不合适可在售后期内申请退换。', '服饰 鞋靴 售后 吊牌 污渍 尺码 退换');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('service', '客服时间', '在线客服服务时间为9:00-23:00，电话客服为工作日9:00-18:00。非服务时间提交的问题会在下一服务时段按顺序处理。', '客服 时间 在线 电话 工作日');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('service', '投诉处理时效', '普通投诉将在24小时内响应，复杂投诉通常在3个工作日内给出处理方案。涉及物流、仓库、财务或商家协同时，处理时间可能延长。', '投诉 处理 时效 24小时 工作日 物流 财务');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('service', '升级人工客服', '当用户涉及资金异常、重复扣款、投诉升级、无法自助处理的售后、疑似账户风险或情绪强烈不满时，应建议转人工客服处理。', '人工客服 升级 资金异常 投诉 售后 账户风险');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('service', '客服承诺边界', '客服只能基于系统状态和平台规则提供答复，不得承诺超出规则的退款、补偿、发货时效、取消成功或库存保留。', '客服 承诺 边界 退款 补偿 发货 库存');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('service', '补偿规则', '补偿仅在平台责任、活动承诺或客服主管审核通过时发放。补偿形式可能为优惠券、积分、运费券或部分现金，不能由普通客服随意承诺。', '补偿 优惠券 积分 运费券 审核 平台责任');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('risk', '隐私安全规则', '客服不得索要用户密码、支付密码、短信验证码、银行卡完整卡号、身份证完整照片等敏感信息。用户主动发送敏感信息时，应提醒其删除或打码。', '隐私 安全 密码 验证码 银行卡 身份证 打码');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('risk', '异常账号处理', '账号存在盗用、刷单、套券、恶意退货、批量下单或支付风控时，部分功能可能被限制。客服只能告知用户按页面提示或人工审核流程处理。', '异常账号 风控 刷单 套券 恶意退货 审核');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('risk', '高风险请求拒绝', '用户要求绕过支付、修改订单金额、伪造物流、伪造发票、泄露他人订单、跳过售后审核或直接退款时，客服必须拒绝并引导走正规流程。', '高风险 拒绝 绕过支付 修改金额 伪造物流 泄露订单');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('risk', '订单归属校验', '查询订单、购物车、地址、退款进度等个人数据前，应要求用户登录并仅返回该账号名下数据。不得根据手机号、姓名等模糊信息泄露他人订单。', '订单归属 登录 个人数据 隐私 手机号 泄露');
INSERT INTO knowledge (category, title, content, keywords) VALUES
('risk', '无法确认的问题', '当知识库和系统数据无法确认答案时，应明确说明需要进一步核实，不得编造政策、库存、物流、退款结果或人工审核结论。', '无法确认 不编造 核实 政策 库存 物流 退款');

COMMIT;

SELECT CONCAT('知识库更新完成，当前条目数: ', COUNT(*)) AS message FROM knowledge;
