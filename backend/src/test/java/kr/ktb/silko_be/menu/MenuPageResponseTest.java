package kr.ktb.silko_be.menu;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Set;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.menu.DrinkOptions.DefaultSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.OptionType;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.store.Store;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;

class MenuPageResponseTest {
    @Test
    void preservesCategoryPageTotals() {
        var store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
        var menu = new Menu(store, MenuCategory.COFFEE, "아이스 아메리카노", "깔끔한 맛", 4500, "stores/key",
            Set.of(Temperature.ICE), DefaultSweetness.MEDIUM, true, true);
        var menuResponse = MenuController.response(menu, null);
        var page = new PageImpl<>(java.util.Collections.nCopies(15, menuResponse), PageRequest.of(1, 20), 35);

        var response = MenuController.PageResponse.from(page);

        assertThat(response.content()).hasSize(15);
        assertThat(response.content().getFirst().description()).isEqualTo("깔끔한 맛");
        assertThat(response.content().getFirst().imageKey()).isEqualTo("stores/key");
        assertThat(response.content().getFirst().availableTemperatures()).containsExactly(Temperature.ICE);
        assertThat(response.content().getFirst().defaultSweetness()).isEqualTo(DefaultSweetness.MEDIUM);
        assertThat(response.content().getFirst().caffeinated()).isTrue();
        assertThat(response.content().getFirst().extraShotAvailable()).isTrue();
        assertThat(response.content().getFirst().availableOptions())
            .filteredOn(option -> option.type() == OptionType.EXTRA_SHOT)
            .extracting(MenuController.OptionResponse::code)
            .containsExactly("NONE", "SHOT_1", "SHOT_2");
        assertThat(response.content().getFirst().availableOptions())
            .filteredOn(option -> option.type() == OptionType.SWEETNESS)
            .extracting(MenuController.OptionResponse::finalSweetness)
            .containsExactly(DrinkOptions.FinalSweetness.LOW, DrinkOptions.FinalSweetness.MEDIUM,
                DrinkOptions.FinalSweetness.HIGH);
        assertThat(response.page()).isEqualTo(1);
        assertThat(response.totalElements()).isEqualTo(35);
        assertThat(response.totalPages()).isEqualTo(2);
        assertThat(response.last()).isTrue();
    }

    @Test
    void requiresAtLeastOneTemperature() {
        var store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));

        assertThatThrownBy(() -> new Menu(store, MenuCategory.COFFEE, "아메리카노", null, 4500, null,
            Set.of(), DefaultSweetness.MEDIUM, true, false))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void excludesExtraShotOptionsWhenUnavailable() {
        var store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
        var menu = new Menu(store, MenuCategory.TEA, "차", null, 4000, null);

        var response = MenuController.response(menu, null);

        assertThat(response.extraShotAvailable()).isFalse();
        assertThat(response.availableOptions()).noneMatch(option -> option.type() == OptionType.EXTRA_SHOT);
    }
}
