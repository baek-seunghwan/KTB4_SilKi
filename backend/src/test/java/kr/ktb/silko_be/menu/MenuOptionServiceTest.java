package kr.ktb.silko_be.menu;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import java.util.List;
import java.util.Set;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.menu.DrinkOptions.DefaultSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.store.Store;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class MenuOptionServiceTest {
    private final MenuOptionGroupRepository repository = mock(MenuOptionGroupRepository.class);
    private final MenuOptionService service = new MenuOptionService(repository);
    private final Store store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));

    @Test
    void createsDefaultsWithOnlyTemperatureRequiringAnAnswer() {
        var menu = menu(Set.of(Temperature.HOT, Temperature.ICE), true);

        service.createDefaults(menu);

        var groups = capturedGroups();
        assertThat(groups).extracting(MenuOptionGroup::getCode)
            .containsExactly("TEMPERATURE", "SIZE", "EXTRA_SHOT", "SWEETNESS");
        assertThat(group(groups, "TEMPERATURE").getValues())
            .extracting(MenuOptionValue::getCode).containsExactly("HOT", "ICE");
        assertThat(group(groups, "TEMPERATURE").getValues())
            .noneMatch(MenuOptionValue::isDefaultValue);
        assertDefault(group(groups, "SIZE"), "REGULAR");
        assertDefault(group(groups, "EXTRA_SHOT"), "NONE");
        assertDefault(group(groups, "SWEETNESS"), "NORMAL");
        assertThat(value(group(groups, "SIZE"), "LARGE").getAdditionalPrice()).isEqualTo(500);
        assertThat(value(group(groups, "EXTRA_SHOT"), "SHOT_2").getAdditionalPrice()).isEqualTo(1_000);
    }

    @Test
    void autoSelectsTheOnlyTemperatureAndOmitsUnavailableShots() {
        var menu = menu(Set.of(Temperature.HOT), false);

        service.createDefaults(menu);

        var groups = capturedGroups();
        assertThat(groups).extracting(MenuOptionGroup::getCode)
            .containsExactly("TEMPERATURE", "SIZE", "SWEETNESS");
        assertDefault(group(groups, "TEMPERATURE"), "HOT");
    }

    @SuppressWarnings("unchecked")
    private List<MenuOptionGroup> capturedGroups() {
        var captor = ArgumentCaptor.forClass(List.class);
        verify(repository).saveAll(captor.capture());
        return (List<MenuOptionGroup>) captor.getValue();
    }

    private Menu menu(Set<Temperature> temperatures, boolean extraShotAvailable) {
        return new Menu(store, MenuCategory.COFFEE, "테스트 메뉴", "설명", 4_500, null,
            temperatures, DefaultSweetness.MEDIUM, true, extraShotAvailable);
    }

    private MenuOptionGroup group(List<MenuOptionGroup> groups, String code) {
        return groups.stream().filter(group -> group.getCode().equals(code)).findFirst().orElseThrow();
    }

    private MenuOptionValue value(MenuOptionGroup group, String code) {
        return group.getValues().stream().filter(value -> value.getCode().equals(code)).findFirst().orElseThrow();
    }

    private void assertDefault(MenuOptionGroup group, String code) {
        assertThat(group.getValues()).filteredOn(MenuOptionValue::isDefaultValue)
            .extracting(MenuOptionValue::getCode).containsExactly(code);
    }
}
