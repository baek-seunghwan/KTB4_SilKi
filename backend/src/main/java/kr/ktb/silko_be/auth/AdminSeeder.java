package kr.ktb.silko_be.auth;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import kr.ktb.silko_be.menu.Menu;
import kr.ktb.silko_be.menu.MenuCategory;
import kr.ktb.silko_be.menu.MenuOptionService;
import kr.ktb.silko_be.menu.MenuRepository;
import kr.ktb.silko_be.menu.DrinkOptions.DefaultSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.store.Store;
import kr.ktb.silko_be.store.StoreRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class AdminSeeder implements ApplicationRunner {
    public static final UUID STORE_ID = UUID.fromString("8c6d2f1a-7b44-4e39-9a21-5f0c8d7e6b10");

    private static final List<MenuSeed> MENUS = List.of(
        menu("아메리카노", MenuCategory.COFFEE, 4_000, both(), DefaultSweetness.LOW, true),
        menu("카페 라떼", MenuCategory.COFFEE, 4_500, both(), DefaultSweetness.LOW, true),
        menu("바닐라 라떼", MenuCategory.COFFEE, 5_000, both(), DefaultSweetness.HIGH, true),
        menu("카라멜 마끼아또", MenuCategory.COFFEE, 5_500, both(), DefaultSweetness.HIGH, true),
        menu("카페 모카", MenuCategory.COFFEE, 5_500, both(), DefaultSweetness.HIGH, true),
        menu("카푸치노", MenuCategory.COFFEE, 4_800, both(), DefaultSweetness.LOW, true),
        menu("콜드 브루", MenuCategory.COFFEE, 5_000, Set.of(Temperature.ICE), DefaultSweetness.LOW, true),
        menu("고구마 라떼", MenuCategory.BEVERAGE, 5_500, both(), DefaultSweetness.HIGH, false),
        menu("녹차 라떼", MenuCategory.BEVERAGE, 5_500, both(), DefaultSweetness.MEDIUM, true),
        menu("초코 라떼", MenuCategory.BEVERAGE, 5_500, both(), DefaultSweetness.HIGH, false),
        menu("딸기 라떼", MenuCategory.BEVERAGE, 6_000, Set.of(Temperature.ICE), DefaultSweetness.HIGH, false),
        menu("레몬 에이드", MenuCategory.BEVERAGE, 5_500, Set.of(Temperature.ICE), DefaultSweetness.HIGH, false),
        menu("자몽 에이드", MenuCategory.BEVERAGE, 5_500, Set.of(Temperature.ICE), DefaultSweetness.HIGH, false),
        menu("청포도 에이드", MenuCategory.BEVERAGE, 5_500, Set.of(Temperature.ICE), DefaultSweetness.HIGH, false),
        menu("복숭아 아이스티", MenuCategory.BEVERAGE, 4_500, Set.of(Temperature.ICE), DefaultSweetness.MEDIUM, false),
        menu("요거트 스무디", MenuCategory.BEVERAGE, 6_000, Set.of(Temperature.ICE), DefaultSweetness.HIGH, false),
        menu("캐모마일", MenuCategory.TEA, 4_500, both(), DefaultSweetness.LOW, false),
        menu("대추차", MenuCategory.TEA, 5_000, Set.of(Temperature.HOT), DefaultSweetness.MEDIUM, false),
        menu("유자차", MenuCategory.TEA, 5_000, Set.of(Temperature.HOT), DefaultSweetness.HIGH, false),
        menu("쌍화차", MenuCategory.TEA, 6_000, Set.of(Temperature.HOT), DefaultSweetness.MEDIUM, false)
    );

    private final AdminUserRepository repository;
    private final StoreRepository storeRepository;
    private final MenuRepository menuRepository;
    private final MenuOptionService optionService;
    private final PasswordEncoder passwordEncoder;
    private final String email;
    private final String password;
    private final String name;

    public AdminSeeder(AdminUserRepository repository, StoreRepository storeRepository,
                       MenuRepository menuRepository, MenuOptionService optionService, PasswordEncoder passwordEncoder,
                       @Value("${app.admin.email}") String email,
                       @Value("${app.admin.password}") String password,
                       @Value("${app.admin.name}") String name) {
        this.repository = repository;
        this.storeRepository = storeRepository;
        this.menuRepository = menuRepository;
        this.optionService = optionService;
        this.passwordEncoder = passwordEncoder;
        this.email = email;
        this.password = password;
        this.name = name;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        var admin = repository.findByEmail(email)
            .orElseGet(() -> repository.save(new AdminUser(email, passwordEncoder.encode(password), name)));
        if (!storeRepository.findAllManagedBy(email).isEmpty()) return;

        var store = storeRepository.save(new Store(STORE_ID, "실키카페 카테부점", admin));
        for (var seed : MENUS) {
            var menu = menuRepository.save(seed.toMenu(store));
            optionService.createDefaults(menu);
        }
    }

    private static MenuSeed menu(String name, MenuCategory category, long price, Set<Temperature> temperatures,
                                 DefaultSweetness sweetness, boolean caffeinated) {
        return new MenuSeed(name, category, price, temperatures, sweetness, caffeinated);
    }

    private static Set<Temperature> both() {
        return Set.of(Temperature.HOT, Temperature.ICE);
    }

    private record MenuSeed(String name, MenuCategory category, long price, Set<Temperature> temperatures,
                            DefaultSweetness sweetness, boolean caffeinated) {
        Menu toMenu(Store store) {
            var id = UUID.nameUUIDFromBytes(("silki-demo-menu:" + name).getBytes(StandardCharsets.UTF_8));
            return new Menu(id, store, category, name, null, price, null, temperatures, sweetness, caffeinated,
                category == MenuCategory.COFFEE);
        }
    }
}
