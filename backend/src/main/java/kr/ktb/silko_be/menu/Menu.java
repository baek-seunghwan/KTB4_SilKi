package kr.ktb.silko_be.menu;

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
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import kr.ktb.silko_be.menu.DrinkOptions.DefaultSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.store.Store;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@Entity
@Table(name = "menus")
public class Menu {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "store_id", nullable = false)
    private Store store;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private MenuCategory category;

    @Column(nullable = false, length = 50)
    private String name;

    @Column(length = 500)
    private String description;

    @Column(name = "supports_hot", nullable = false)
    private boolean supportsHot;

    @Column(name = "supports_ice", nullable = false)
    private boolean supportsIce;

    @Enumerated(EnumType.STRING)
    @Column(name = "default_sweetness", nullable = false)
    private DefaultSweetness defaultSweetness;

    @Column(nullable = false)
    private boolean caffeinated;

    @Column(name = "supports_extra_shot", nullable = false)
    private boolean extraShotAvailable;

    @Column(nullable = false)
    private long price;

    @Column(name = "image_key")
    private String imageKey;

    @Enumerated(EnumType.STRING)
    @Column(name = "sales_status", nullable = false)
    private SalesStatus salesStatus;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected Menu() {}

    public Menu(Store store, MenuCategory category, String name, String description, long price, String imageKey) {
        this(store, category, name, description, price, imageKey,
            Set.of(Temperature.HOT, Temperature.ICE), DefaultSweetness.MEDIUM, false, false);
    }

    public Menu(Store store, MenuCategory category, String name, String description, long price, String imageKey,
                Set<Temperature> availableTemperatures, DefaultSweetness defaultSweetness, boolean caffeinated,
                boolean extraShotAvailable) {
        this(UUID.randomUUID(), store, category, name, description, price, imageKey, availableTemperatures,
            defaultSweetness, caffeinated, extraShotAvailable);
    }

    public Menu(UUID id, Store store, MenuCategory category, String name, String description, long price,
                String imageKey, Set<Temperature> availableTemperatures, DefaultSweetness defaultSweetness,
                boolean caffeinated, boolean extraShotAvailable) {
        this.id = id;
        this.store = store;
        this.category = category;
        this.name = name;
        this.description = description;
        this.price = price;
        this.imageKey = imageKey;
        this.salesStatus = SalesStatus.AVAILABLE;
        setDrinkOptions(availableTemperatures, defaultSweetness, caffeinated, extraShotAvailable);
    }

    public void update(MenuCategory category, String name, String description, long price, String imageKey,
                       Set<Temperature> availableTemperatures, DefaultSweetness defaultSweetness, boolean caffeinated,
                       boolean extraShotAvailable) {
        this.category = category;
        this.name = name;
        this.description = description;
        this.price = price;
        this.imageKey = imageKey;
        setDrinkOptions(availableTemperatures, defaultSweetness, caffeinated, extraShotAvailable);
    }

    private void setDrinkOptions(Set<Temperature> temperatures, DefaultSweetness sweetness, boolean caffeinated,
                                 boolean extraShotAvailable) {
        if (temperatures == null || temperatures.isEmpty()) {
            throw new IllegalArgumentException("주문 가능한 온도가 하나 이상 필요합니다.");
        }
        supportsHot = temperatures.contains(Temperature.HOT);
        supportsIce = temperatures.contains(Temperature.ICE);
        defaultSweetness = Objects.requireNonNull(sweetness);
        this.caffeinated = caffeinated;
        this.extraShotAvailable = extraShotAvailable;
    }

    public void changeSalesStatus(SalesStatus status) { this.salesStatus = status; }

    public UUID getId() { return id; }
    public MenuCategory getCategory() { return category; }
    public String getName() { return name; }
    public String getDescription() { return description; }
    public Set<Temperature> getAvailableTemperatures() {
        var temperatures = EnumSet.noneOf(Temperature.class);
        if (supportsHot) temperatures.add(Temperature.HOT);
        if (supportsIce) temperatures.add(Temperature.ICE);
        return temperatures;
    }
    public boolean supports(Temperature temperature) { return getAvailableTemperatures().contains(temperature); }
    public DefaultSweetness getDefaultSweetness() { return defaultSweetness; }
    public boolean isCaffeinated() { return caffeinated; }
    public boolean isExtraShotAvailable() { return extraShotAvailable; }
    public long getPrice() { return price; }
    public String getImageKey() { return imageKey; }
    public SalesStatus getSalesStatus() { return salesStatus; }
}
