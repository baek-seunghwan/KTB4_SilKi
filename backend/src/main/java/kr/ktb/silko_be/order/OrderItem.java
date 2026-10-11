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
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.ktb.silko_be.menu.DrinkOptions.Choice;
import kr.ktb.silko_be.menu.DrinkOptions.FinalSweetness;

@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private CustomerOrder order;

    @Column(name = "menu_id", nullable = false)
    private UUID menuId;

    @Column(name = "menu_name", nullable = false, length = 50)
    private String menuName;

    @Column(name = "unit_price", nullable = false)
    private long unitPrice;

    @Column(nullable = false)
    private int quantity;

    @Column(nullable = false)
    private long subtotal;

    @Enumerated(EnumType.STRING)
    @Column(name = "final_sweetness")
    private FinalSweetness finalSweetness;

    @OneToMany(mappedBy = "orderItem", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<OrderItemOption> options = new ArrayList<>();

    protected OrderItem() {}

    OrderItem(CustomerOrder order, UUID menuId, String menuName, long basePrice, int quantity,
              FinalSweetness finalSweetness, Choice... choices) {
        this.id = UUID.randomUUID();
        this.order = order;
        this.menuId = menuId;
        this.menuName = menuName;
        this.quantity = quantity;
        this.finalSweetness = finalSweetness;
        this.unitPrice = basePrice;
        for (var choice : choices) {
            options.add(new OrderItemOption(this, choice));
            unitPrice = Math.addExact(unitPrice, choice.additionalPrice());
        }
        this.subtotal = Math.multiplyExact(unitPrice, quantity);
    }

    public String getMenuName() { return menuName; }
    public long getBasePrice() {
        return Math.subtractExact(unitPrice,
            options.stream().mapToLong(OrderItemOption::getAdditionalPrice).sum());
    }
    public long getUnitPrice() { return unitPrice; }
    public int getQuantity() { return quantity; }
    public long getSubtotal() { return subtotal; }
    public FinalSweetness getFinalSweetness() { return finalSweetness; }
    public List<OrderItemOption> getOptions() { return options; }
}
