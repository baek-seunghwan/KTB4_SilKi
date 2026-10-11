package kr.ktb.silko_be.order;

public enum OrderStatus {
    RECEIVED(false, "주문이 접수되었습니다. 카운터에서 결제해주세요."),
    PREPARING(false, "음료를 준비하고 있습니다."),
    COMPLETED(true, "음료가 준비되었습니다. 픽업해주세요.");

    private final boolean pickupReady;
    private final String customerMessage;

    OrderStatus(boolean pickupReady, String customerMessage) {
        this.pickupReady = pickupReady;
        this.customerMessage = customerMessage;
    }

    public boolean canChangeTo(OrderStatus next) {
        return (this == RECEIVED && next == PREPARING)
            || (this == PREPARING && next == COMPLETED);
    }

    public boolean isPickupReady() {
        return pickupReady;
    }

    public String getCustomerMessage() {
        return customerMessage;
    }
}
