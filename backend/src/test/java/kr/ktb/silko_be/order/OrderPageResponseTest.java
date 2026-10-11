package kr.ktb.silko_be.order;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Collections;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;

class OrderPageResponseTest {
    @Test
    void preservesOrderPageTotals() {
        var page = new PageImpl<>(Collections.nCopies(15, "order"), PageRequest.of(1, 20), 35);

        var response = AdminOrderController.PageResponse.from(page);

        assertThat(response.content()).hasSize(15);
        assertThat(response.page()).isEqualTo(1);
        assertThat(response.size()).isEqualTo(20);
        assertThat(response.totalElements()).isEqualTo(35);
        assertThat(response.totalPages()).isEqualTo(2);
        assertThat(response.last()).isTrue();
    }
}
