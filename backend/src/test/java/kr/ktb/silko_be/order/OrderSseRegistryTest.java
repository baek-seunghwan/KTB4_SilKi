package kr.ktb.silko_be.order;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.ktb.silko_be.order.OrderDtos.OrderStatusResponse;
import kr.ktb.silko_be.session.FulfillmentType;
import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

class OrderSseRegistryTest {
    @Test
    void sendsPickupEventAfterCompletedStatusAndClosesConnection() {
        var emitter = new RecordingSseEmitter();
        var registry = new OrderSseRegistry(() -> emitter);
        var orderId = UUID.randomUUID();
        registry.subscribeOrder(orderId);
        var status = new OrderStatusResponse(orderId, 12L, OrderStatus.COMPLETED,
            FulfillmentType.TAKEOUT, true, "음료가 준비되었습니다. 픽업해주세요.",
            OffsetDateTime.parse("2026-08-20T13:00:00+09:00"));

        registry.statusChanged(status);

        assertThat(emitter.eventNames).containsExactly("ORDER_STATUS_CHANGED", "PICKUP_READY");
        assertThat(emitter.completed).isTrue();
    }

    @Test
    void keepsConnectionOpenBeforePickupIsReady() {
        var emitter = new RecordingSseEmitter();
        var registry = new OrderSseRegistry(() -> emitter);
        var orderId = UUID.randomUUID();
        registry.subscribeOrder(orderId);
        var status = new OrderStatusResponse(orderId, 12L, OrderStatus.PREPARING,
            FulfillmentType.DINE_IN, false, "음료를 준비하고 있습니다.",
            OffsetDateTime.parse("2026-08-20T13:00:00+09:00"));

        registry.statusChanged(status);

        assertThat(emitter.eventNames).containsExactly("ORDER_STATUS_CHANGED");
        assertThat(emitter.completed).isFalse();
    }

    private static final class RecordingSseEmitter extends SseEmitter {
        private final List<String> eventNames = new ArrayList<>();
        private boolean completed;

        @Override
        public void send(SseEventBuilder builder) throws IOException {
            builder.build().stream()
                .map(item -> item.getData().toString())
                .filter(data -> data.startsWith("event:"))
                .map(data -> data.substring("event:".length()).lines().findFirst().orElseThrow().trim())
                .forEach(eventNames::add);
        }

        @Override
        public void complete() {
            completed = true;
            super.complete();
        }
    }
}
