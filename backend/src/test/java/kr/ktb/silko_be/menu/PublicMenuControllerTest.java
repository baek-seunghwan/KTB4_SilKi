package kr.ktb.silko_be.menu;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.storage.ImageStorage;
import kr.ktb.silko_be.store.Store;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageImpl;

class PublicMenuControllerTest {
    @Test
    void exposesOnlyOptionsThatNeedAnAnswerAsRequiredSelections() {
        var menuService = mock(MenuService.class);
        var optionService = mock(MenuOptionService.class);
        var imageStorage = mock(ImageStorage.class);
        var store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
        var menu = new Menu(store, MenuCategory.COFFEE, "아메리카노", "깔끔하고 진한 커피", 4000, null);
        var temperature = new MenuOptionGroup(menu, "TEMPERATURE", "온도", true, 1, 1, 0);
        temperature.addValue("HOT", "따뜻하게", 0, false, 0);
        temperature.addValue("ICE", "차갑게", 0, false, 1);
        var size = new MenuOptionGroup(menu, "SIZE", "사이즈", true, 1, 1, 1);
        var regular = size.addValue("REGULAR", "레귤러", 0, true, 0);
        size.addValue("LARGE", "라지", 500, false, 1);
        when(menuService.listPublic(store.getId(), MenuCategory.COFFEE, 0, 20))
            .thenReturn(new PageImpl<>(List.of(menu)));
        when(optionService.findByMenuIds(List.of(menu.getId())))
            .thenReturn(java.util.Map.of(menu.getId(), List.of(temperature, size)));

        var response = new PublicMenuController(menuService, optionService, imageStorage)
            .list(store.getId(), MenuCategory.COFFEE, 0, 20);

        var publicMenu = response.content().getFirst();
        assertThat(publicMenu.description()).isEqualTo("깔끔하고 진한 커피");
        assertThat(publicMenu.availableOptions()).isNotEmpty();
        var options = publicMenu.options();
        assertThat(options).hasSize(2);
        assertThat(options.getFirst().requiresSelection()).isTrue();
        assertThat(options.getFirst().autoSelectedOptionId()).isNull();
        assertThat(options.get(1).requiresSelection()).isFalse();
        assertThat(options.get(1).autoSelectedOptionId()).isEqualTo(regular.getId());
    }

    @Test
    void resolvesAnAiCandidateByStoreAndMenuIdWithAuthoritativeOptionValueIds() {
        var menuService = mock(MenuService.class);
        var optionService = mock(MenuOptionService.class);
        var imageStorage = mock(ImageStorage.class);
        var store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
        var menu = new Menu(store, MenuCategory.COFFEE, "카페 라떼", "부드러운 라떼", 4500, null);
        var temperature = new MenuOptionGroup(menu, "TEMPERATURE", "온도", true, 1, 1, 0);
        var hot = temperature.addValue("HOT", "따뜻하게", 0, false, 0);
        var ice = temperature.addValue("ICE", "차갑게", 0, false, 1);
        when(menuService.getPublic(store.getId(), menu.getId())).thenReturn(menu);
        when(optionService.findByMenuIds(List.of(menu.getId())))
            .thenReturn(java.util.Map.of(menu.getId(), List.of(temperature)));

        var response = new PublicMenuController(menuService, optionService, imageStorage)
            .get(store.getId(), menu.getId());

        verify(menuService).getPublic(store.getId(), menu.getId());
        assertThat(response.id()).isEqualTo(menu.getId());
        assertThat(response.name()).isEqualTo("카페 라떼");
        assertThat(response.options()).singleElement().satisfies(group -> {
            assertThat(group.code()).isEqualTo("TEMPERATURE");
            assertThat(group.requiresSelection()).isTrue();
            assertThat(group.autoSelectedOptionId()).isNull();
            assertThat(group.values()).extracting(PublicMenuController.OptionValueResponse::id)
                .containsExactly(hot.getId(), ice.getId());
        });
    }
}
