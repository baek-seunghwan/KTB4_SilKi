package kr.ktb.silko_be.cart;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.ManyToMany;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import kr.ktb.silko_be.menu.Menu;
import kr.ktb.silko_be.menu.MenuOptionValue;
import kr.ktb.silko_be.session.OrderSession;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@Entity
@Table(name = "cart_items")
public class CartItem {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_session_id", nullable = false)
    private OrderSession orderSession;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "menu_id", nullable = false)
    private Menu menu;

    @Column(nullable = false)
    private int quantity;

    @ManyToMany
    @JoinTable(
        name = "cart_item_options",
        joinColumns = @JoinColumn(name = "cart_item_id"),
        inverseJoinColumns = @JoinColumn(name = "option_value_id")
    )
    @OrderBy("displayOrder ASC")
    private Set<MenuOptionValue> selectedOptions = new LinkedHashSet<>();

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected CartItem() {}

    public CartItem(OrderSession orderSession, Menu menu, int quantity) {
        this.id = UUID.randomUUID();
        this.orderSession = orderSession;
        this.menu = menu;
        this.quantity = quantity;
    }

    public void addOption(MenuOptionValue option) {
        selectedOptions.add(option);
    }

    public void update(int quantity, Collection<MenuOptionValue> options) {
        this.quantity = quantity;
        selectedOptions.clear();
        selectedOptions.addAll(options);
    }

    public UUID getId() { return id; }
    public Menu getMenu() { return menu; }
    public int getQuantity() { return quantity; }
    public Set<MenuOptionValue> getSelectedOptions() {
        return Collections.unmodifiableSet(selectedOptions);
    }
}
