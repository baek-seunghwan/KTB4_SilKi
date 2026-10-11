package kr.ktb.silko_be.cart;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.util.List;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.menu.Menu;
import kr.ktb.silko_be.menu.MenuCategory;
import kr.ktb.silko_be.menu.MenuOptionGroup;
import kr.ktb.silko_be.session.OrderSession;
import kr.ktb.silko_be.storage.ImageStorage;
import kr.ktb.silko_be.store.Store;
import org.junit.jupiter.api.Test;

class CartControllerTest {
    @Test
    void calculatesCartTotalsFromAuthoritativeMenuAndOptionPrices() {
        var service = mock(CartService.class);
        var imageStorage = mock(ImageStorage.class);
        var store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
        var session = new OrderSession(store, OffsetDateTime.now().plusMinutes(30));
        var menu = new Menu(store, MenuCategory.COFFEE, "카페 라떼", "부드러운 라떼", 4500, null);
        var size = new MenuOptionGroup(menu, "SIZE", "사이즈", true, 1, 1, 0);
        var large = size.addValue("LARGE", "라지", 500, false, 0);
        var item = new CartItem(session, menu, 2);
        item.addOption(large);
        when(service.get(session.getId())).thenReturn(new CartService.CartSnapshot(session, List.of(item)));

        var response = new CartController(service, imageStorage).get(session.getId());

        assertThat(response.cartVersion()).isZero();
        assertThat(response.totalQuantity()).isEqualTo(2);
        assertThat(response.totalPrice()).isEqualTo(10_000);
        assertThat(response.items().getFirst().unitPrice()).isEqualTo(5_000);
        assertThat(response.items().getFirst().options().getFirst().optionGroupCode()).isEqualTo("SIZE");
    }
}
