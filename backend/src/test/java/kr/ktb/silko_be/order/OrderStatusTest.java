package kr.ktb.silko_be.order;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class OrderStatusTest {
    @Test
    void onlyAllowsForwardTransitions() {
        assertThat(OrderStatus.RECEIVED.canChangeTo(OrderStatus.PREPARING)).isTrue();
        assertThat(OrderStatus.PREPARING.canChangeTo(OrderStatus.COMPLETED)).isTrue();
        assertThat(OrderStatus.COMPLETED.canChangeTo(OrderStatus.PREPARING)).isFalse();
        assertThat(OrderStatus.RECEIVED.canChangeTo(OrderStatus.COMPLETED)).isFalse();
    }

    @Test
    void exposesCustomerPickupGuidance() {
        assertThat(OrderStatus.RECEIVED.isPickupReady()).isFalse();
        assertThat(OrderStatus.RECEIVED.getCustomerMessage()).contains("카운터에서 결제");
        assertThat(OrderStatus.PREPARING.isPickupReady()).isFalse();
        assertThat(OrderStatus.COMPLETED.isPickupReady()).isTrue();
        assertThat(OrderStatus.COMPLETED.getCustomerMessage()).contains("픽업");
    }
}
