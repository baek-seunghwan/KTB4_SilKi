package kr.ktb.silko_be.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Optional;
import kr.ktb.silko_be.menu.Menu;
import kr.ktb.silko_be.menu.MenuCategory;
import kr.ktb.silko_be.menu.MenuOptionService;
import kr.ktb.silko_be.menu.MenuRepository;
import kr.ktb.silko_be.store.Store;
import kr.ktb.silko_be.store.StoreRepository;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.crypto.password.PasswordEncoder;

class AdminSeederTest {
    @Test
    void seedsStoreMenusAndCoffeeOnlyShotOptions() {
        var adminRepository = mock(AdminUserRepository.class);
        var storeRepository = mock(StoreRepository.class);
        var menuRepository = mock(MenuRepository.class);
        var optionService = mock(MenuOptionService.class);
        var passwordEncoder = mock(PasswordEncoder.class);
        var admin = new AdminUser("admin@test.com", "hash", "관리자");
        when(adminRepository.findByEmail("admin@test.com")).thenReturn(Optional.of(admin));
        when(storeRepository.findAllManagedBy("admin@test.com")).thenReturn(List.of());
        when(storeRepository.save(any())).thenAnswer(call -> call.getArgument(0));
        when(menuRepository.save(any())).thenAnswer(call -> call.getArgument(0));

        new AdminSeeder(adminRepository, storeRepository, menuRepository, optionService, passwordEncoder,
            "admin@test.com", "password", "관리자").run(null);

        var store = ArgumentCaptor.forClass(Store.class);
        verify(storeRepository).save(store.capture());
        assertThat(store.getValue().getName()).isEqualTo("실키카페 카테부점");
        assertThat(store.getValue().getId()).isEqualTo(AdminSeeder.STORE_ID);

        var menus = ArgumentCaptor.forClass(Menu.class);
        verify(menuRepository, times(20)).save(menus.capture());
        assertThat(menus.getAllValues()).hasSize(20)
            .allSatisfy(menu -> assertThat(menu.isExtraShotAvailable())
                .isEqualTo(menu.getCategory() == MenuCategory.COFFEE));
        assertThat(menus.getAllValues()).filteredOn(Menu::isExtraShotAvailable).hasSize(7);
        assertThat(menus.getAllValues()).extracting(Menu::getId).doesNotHaveDuplicates();
        verify(optionService, times(20)).createDefaults(any());
    }
}
