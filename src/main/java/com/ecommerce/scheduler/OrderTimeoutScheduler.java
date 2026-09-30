package com.ecommerce.scheduler;

import com.ecommerce.entity.Order;
import com.ecommerce.repository.OrderRepository;
import com.ecommerce.service.OrderService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 待支付订单超时自动取消调度器。
 *
 * 多实例部署安全设计：
 * 1. 查询使用 SELECT ... FOR UPDATE SKIP LOCKED，各实例各取各的，互不阻塞、不重复处理
 * 2. 取消使用乐观更新 UPDATE ... WHERE status=0，通过影响行数判断是否抢到
 * 3. 单条订单处理失败不影响其他订单，失败订单下次轮询自动重试
 *
 * 性能设计：
 * 1. 每次只取一批（默认100条），避免长事务和内存溢出
 * 2. 循环处理直到无超时订单，单次任务内可处理多批
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OrderTimeoutScheduler {

    private final OrderRepository orderRepository;
    private final OrderService orderService;

    /** 单次批量处理上限 */
    @Value("${order.timeout-scheduler.batch-size:100}")
    private int batchSize;

    /**
     * 每分钟扫描一次超时未支付订单。
     * 使用 fixedDelay 保证上一轮执行完毕后再开始下一轮，避免任务堆积。
     */
    @Scheduled(fixedDelayString = "${order.timeout-scheduler.fixed-delay-ms:60000}")
    public void cancelExpiredOrders() {
        LocalDateTime now = LocalDateTime.now();
        long startTime = System.currentTimeMillis();
        int totalCancelled = 0;
        int totalFailed = 0;
        int totalSkipped = 0;

        try {
            while (true) {
                List<Order> expiredOrders = orderRepository.findExpiredPendingOrders(now, batchSize);
                if (expiredOrders.isEmpty()) {
                    break;
                }

                for (Order order : expiredOrders) {
                    try {
                        boolean cancelled = orderService.cancelExpiredOrder(order.getId());
                        if (cancelled) {
                            totalCancelled++;
                        } else {
                            totalSkipped++;
                        }
                    } catch (Exception e) {
                        totalFailed++;
                        log.error("Failed to cancel expired order: orderId={}", order.getId(), e);
                        // 单条失败不中断，继续处理下一条；该订单下次轮询重试
                    }
                }

                // 若本批数量小于 batchSize，说明没有更多超时订单，退出循环
                if (expiredOrders.size() < batchSize) {
                    break;
                }
            }
        } catch (Exception e) {
            log.error("Order timeout scheduler batch query failed", e);
        }

        long cost = System.currentTimeMillis() - startTime;
        if (totalCancelled > 0 || totalFailed > 0 || totalSkipped > 0) {
            log.info("Order timeout scheduler finished: cancelled={}, failed={}, skipped={}, cost={}ms",
                    totalCancelled, totalFailed, totalSkipped, cost);
        } else {
            log.debug("Order timeout scheduler found no expired orders, cost={}ms", cost);
        }
    }
}
