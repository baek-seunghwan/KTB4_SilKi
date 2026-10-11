package kr.ktb.silko_be.order;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.ktb.silko_be.menu.DrinkOptions.Choice;
import kr.ktb.silko_be.menu.DrinkOptions.FinalSweetness;
import kr.ktb.silko_be.session.FulfillmentType;
import kr.ktb.silko_be.store.Store;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@Entity
@Table(name = "orders")
public class CustomerOrder {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "store_id", nullable = false)
    private Store store;

    @Column(name = "order_number", nullable = false, unique = true)
    private long orderNumber;

    @Column(name = "idempotency_key", nullable = false, length = 100)
    private String idempotencyKey;

    @Column(name = "order_session_id")
    private UUID orderSessionId;

    @Enumerated(EnumType.STRING)
    @Column(name = "fulfillment_type", length = 20)
    private FulfillmentType fulfillmentType;

    @Enumerated(EnumType.STRING)
    @Column(name = "payment_method", nullable = false, length = 30)
    private PaymentMethod paymentMethod;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "total_price", nullable = false)
    private long totalPrice;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<OrderItem> items = new ArrayList<>();

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected CustomerOrder() {}

    public CustomerOrder(Store store, long orderNumber, String idempotencyKey) {
        this.id = UUID.randomUUID();
        this.store = store;
        this.orderNumber = orderNumber;
        this.idempotencyKey = idempotencyKey;
        this.paymentMethod = PaymentMethod.PAY_AT_COUNTER;
        this.status = OrderStatus.RECEIVED;
    }

    public CustomerOrder(Store store, long orderNumber, String idempotencyKey, UUID orderSessionId,
                         FulfillmentType fulfillmentType, PaymentMethod paymentMethod) {
        this(store, orderNumber, idempotencyKey);
        this.orderSessionId = orderSessionId;
        this.fulfillmentType = fulfillmentType;
        this.paymentMethod = paymentMethod;
    }

    public void addItem(UUID menuId, String menuName, long basePrice, int quantity,
                        FinalSweetness finalSweetness, Choice... choices) {
        var item = new OrderItem(this, menuId, menuName, basePrice, quantity, finalSweetness, choices);
        items.add(item);
        totalPrice = Math.addExact(totalPrice, item.getSubtotal());
    }

    public void changeStatus(OrderStatus status) { this.status = status; }

    public UUID getId() { return id; }
    public UUID getOrderSessionId() { return orderSessionId; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public FulfillmentType getFulfillmentType() { return fulfillmentType; }
    public PaymentMethod getPaymentMethod() { return paymentMethod; }
    public long getOrderNumber() { return orderNumber; }
    public OrderStatus getStatus() { return status; }
    public long getTotalPrice() { return totalPrice; }
    public List<OrderItem> getItems() { return items; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getUpdatedAt() { return updatedAt; }
}
