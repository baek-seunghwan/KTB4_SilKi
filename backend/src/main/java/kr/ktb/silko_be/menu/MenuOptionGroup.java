package kr.ktb.silko_be.menu;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "menu_option_groups")
public class MenuOptionGroup {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "menu_id", nullable = false)
    private Menu menu;

    @Column(nullable = false, length = 30)
    private String code;

    @Column(nullable = false, length = 50)
    private String name;

    @Column(nullable = false)
    private boolean required;

    @Column(name = "min_selections", nullable = false)
    private int minSelections;

    @Column(name = "max_selections", nullable = false)
    private int maxSelections;

    @Column(name = "display_order", nullable = false)
    private int displayOrder;

    @OneToMany(mappedBy = "optionGroup", cascade = CascadeType.ALL, orphanRemoval = true)
    @OrderBy("displayOrder ASC")
    private List<MenuOptionValue> values = new ArrayList<>();

    protected MenuOptionGroup() {}

    public MenuOptionGroup(Menu menu, String code, String name, boolean required,
                           int minSelections, int maxSelections, int displayOrder) {
        this.id = UUID.randomUUID();
        this.menu = menu;
        this.code = code;
        this.name = name;
        this.required = required;
        this.minSelections = minSelections;
        this.maxSelections = maxSelections;
        this.displayOrder = displayOrder;
    }

    public MenuOptionValue addValue(String code, String name, long additionalPrice,
                                    boolean defaultValue, int displayOrder) {
        var value = new MenuOptionValue(this, code, name, additionalPrice, defaultValue, displayOrder);
        values.add(value);
        return value;
    }

    public UUID getId() { return id; }
    public UUID getMenuId() { return menu.getId(); }
    public String getCode() { return code; }
    public String getName() { return name; }
    public boolean isRequired() { return required; }
    public int getMinSelections() { return minSelections; }
    public int getMaxSelections() { return maxSelections; }
    public int getDisplayOrder() { return displayOrder; }
    public List<MenuOptionValue> getValues() { return Collections.unmodifiableList(values); }
}
