package kr.ktb.silko_be.session;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.UUID;
import kr.ktb.silko_be.store.Store;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@Entity
@Table(name = "order_sessions")
public class OrderSession {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "store_id", nullable = false)
    private Store store;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderSessionStatus status;

    @Column(name = "cart_version", nullable = false)
    private long cartVersion;

    @Enumerated(EnumType.STRING)
    @Column(name = "fulfillment_type", length = 20)
    private FulfillmentType fulfillmentType;

    @Column(name = "expires_at", nullable = false)
    private OffsetDateTime expiresAt;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected OrderSession() {}

    public OrderSession(Store store, OffsetDateTime expiresAt) {
        this.id = UUID.randomUUID();
        this.store = store;
        this.status = OrderSessionStatus.ACTIVE;
        this.cartVersion = 0;
        this.expiresAt = expiresAt;
    }

    public UUID getId() { return id; }
    public UUID getStoreId() { return store.getId(); }
    public OrderSessionStatus getStatus() { return status; }
    public long getCartVersion() { return cartVersion; }
    public FulfillmentType getFulfillmentType() { return fulfillmentType; }
    public OffsetDateTime getExpiresAt() { return expiresAt; }

    public void incrementCartVersion() {
        cartVersion = Math.incrementExact(cartVersion);
    }

    public boolean selectFulfillment(FulfillmentType fulfillmentType) {
        if (this.fulfillmentType == fulfillmentType) {
            return false;
        }
        this.fulfillmentType = fulfillmentType;
        incrementCartVersion();
        return true;
    }

    public void markOrdered() {
        if (status != OrderSessionStatus.ACTIVE) {
            throw new IllegalStateException("Only an active order session can be completed");
        }
        status = OrderSessionStatus.ORDERED;
    }
}
