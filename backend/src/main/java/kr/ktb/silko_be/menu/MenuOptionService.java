package kr.ktb.silko_be.menu;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import kr.ktb.silko_be.menu.DrinkOptions.DrinkSize;
import kr.ktb.silko_be.menu.DrinkOptions.ExtraShot;
import kr.ktb.silko_be.menu.DrinkOptions.SweetnessAdjustment;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MenuOptionService {
    private final MenuOptionGroupRepository repository;

    public MenuOptionService(MenuOptionGroupRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void createDefaults(Menu menu) {
        var groups = new ArrayList<MenuOptionGroup>();
        groups.add(temperatureGroup(menu));
        groups.add(sizeGroup(menu));
        if (menu.isExtraShotAvailable()) groups.add(extraShotGroup(menu));
        groups.add(sweetnessGroup(menu));
        repository.saveAll(groups);
    }

    @Transactional(readOnly = true)
    public Map<UUID, List<MenuOptionGroup>> findByMenuIds(Collection<UUID> menuIds) {
        if (menuIds.isEmpty()) return Map.of();
        return repository.findAllByMenu_IdInOrderByDisplayOrderAsc(menuIds).stream()
            .collect(Collectors.groupingBy(MenuOptionGroup::getMenuId));
    }

    private MenuOptionGroup temperatureGroup(Menu menu) {
        var temperatures = menu.getAvailableTemperatures();
        var group = new MenuOptionGroup(menu, "TEMPERATURE", "온도", true, 1, 1, 0);
        if (temperatures.contains(Temperature.HOT)) {
            group.addValue(Temperature.HOT.code(), Temperature.HOT.displayName(),
                Temperature.HOT.additionalPrice(), temperatures.size() == 1, 0);
        }
        if (temperatures.contains(Temperature.ICE)) {
            group.addValue(Temperature.ICE.code(), Temperature.ICE.displayName(),
                Temperature.ICE.additionalPrice(), temperatures.size() == 1, 1);
        }
        return group;
    }

    private MenuOptionGroup sizeGroup(Menu menu) {
        var group = new MenuOptionGroup(menu, "SIZE", "사이즈", true, 1, 1, 1);
        group.addValue(DrinkSize.REGULAR.code(), DrinkSize.REGULAR.displayName(),
            DrinkSize.REGULAR.additionalPrice(), true, 0);
        group.addValue(DrinkSize.LARGE.code(), DrinkSize.LARGE.displayName(),
            DrinkSize.LARGE.additionalPrice(), false, 1);
        return group;
    }

    private MenuOptionGroup extraShotGroup(Menu menu) {
        var group = new MenuOptionGroup(menu, "EXTRA_SHOT", "샷 추가", false, 0, 1, 2);
        int displayOrder = 0;
        for (var option : ExtraShot.values()) {
            group.addValue(option.code(), option.displayName(), option.additionalPrice(),
                option == ExtraShot.NONE, displayOrder++);
        }
        return group;
    }

    private MenuOptionGroup sweetnessGroup(Menu menu) {
        var group = new MenuOptionGroup(menu, "SWEETNESS", "당도", false, 0, 1, 3);
        int displayOrder = 0;
        for (var option : SweetnessAdjustment.values()) {
            group.addValue(option.code(), option.displayName(), option.additionalPrice(),
                option == SweetnessAdjustment.NORMAL, displayOrder++);
        }
        return group;
    }
}
