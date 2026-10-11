package kr.ktb.silko_be.order;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.util.UUID;
import kr.ktb.silko_be.menu.DrinkOptions.Choice;
import kr.ktb.silko_be.menu.DrinkOptions.OptionType;

@Entity
@Table(name = "order_item_options")
public class OrderItemOption {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_item_id", nullable = false)
    private OrderItem orderItem;

    @Enumerated(EnumType.STRING)
    @Column(name = "option_type", nullable = false)
    private OptionType optionType;

    @Column(name = "option_code", nullable = false, length = 20)
    private String optionCode;

    @Column(name = "option_name", nullable = false, length = 50)
    private String optionName;

    @Column(name = "additional_price", nullable = false)
    private long additionalPrice;

    protected OrderItemOption() {}

    OrderItemOption(OrderItem orderItem, Choice choice) {
        this.id = UUID.randomUUID();
        this.orderItem = orderItem;
        this.optionType = choice.type();
        this.optionCode = choice.code();
        this.optionName = choice.displayName();
        this.additionalPrice = choice.additionalPrice();
    }

    public OptionType getOptionType() { return optionType; }
    public String getOptionCode() { return optionCode; }
    public String getOptionName() { return optionName; }
    public long getAdditionalPrice() { return additionalPrice; }
}
