package kr.ktb.silko_be.menu;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "menu_option_values")
public class MenuOptionValue {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "option_group_id", nullable = false)
    private MenuOptionGroup optionGroup;

    @Column(nullable = false, length = 30)
    private String code;

    @Column(nullable = false, length = 50)
    private String name;

    @Column(name = "additional_price", nullable = false)
    private long additionalPrice;

    @Column(name = "is_default", nullable = false)
    private boolean defaultValue;

    @Column(name = "display_order", nullable = false)
    private int displayOrder;

    protected MenuOptionValue() {}

    MenuOptionValue(MenuOptionGroup optionGroup, String code, String name, long additionalPrice,
                    boolean defaultValue, int displayOrder) {
        this.id = UUID.randomUUID();
        this.optionGroup = optionGroup;
        this.code = code;
        this.name = name;
        this.additionalPrice = additionalPrice;
        this.defaultValue = defaultValue;
        this.displayOrder = displayOrder;
    }

    public UUID getId() { return id; }
    public UUID getOptionGroupId() { return optionGroup.getId(); }
    public String getOptionGroupCode() { return optionGroup.getCode(); }
    public String getOptionGroupName() { return optionGroup.getName(); }
    public String getCode() { return code; }
    public String getName() { return name; }
    public long getAdditionalPrice() { return additionalPrice; }
    public boolean isDefaultValue() { return defaultValue; }
    public int getDisplayOrder() { return displayOrder; }
}
