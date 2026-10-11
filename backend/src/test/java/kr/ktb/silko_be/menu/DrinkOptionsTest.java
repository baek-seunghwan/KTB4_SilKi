package kr.ktb.silko_be.menu;

import static org.assertj.core.api.Assertions.assertThat;

import kr.ktb.silko_be.menu.DrinkOptions.DefaultSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.FinalSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.SweetnessAdjustment;
import org.junit.jupiter.api.Test;

class DrinkOptionsTest {
    @Test
    void adjustsAllDefaultSweetnessLevels() {
        assertThat(DefaultSweetness.LOW.adjust(SweetnessAdjustment.LESS)).isEqualTo(FinalSweetness.VERY_LOW);
        assertThat(DefaultSweetness.LOW.adjust(SweetnessAdjustment.NORMAL)).isEqualTo(FinalSweetness.LOW);
        assertThat(DefaultSweetness.LOW.adjust(SweetnessAdjustment.MORE)).isEqualTo(FinalSweetness.MEDIUM);
        assertThat(DefaultSweetness.MEDIUM.adjust(SweetnessAdjustment.LESS)).isEqualTo(FinalSweetness.LOW);
        assertThat(DefaultSweetness.MEDIUM.adjust(SweetnessAdjustment.NORMAL)).isEqualTo(FinalSweetness.MEDIUM);
        assertThat(DefaultSweetness.MEDIUM.adjust(SweetnessAdjustment.MORE)).isEqualTo(FinalSweetness.HIGH);
        assertThat(DefaultSweetness.HIGH.adjust(SweetnessAdjustment.LESS)).isEqualTo(FinalSweetness.MEDIUM);
        assertThat(DefaultSweetness.HIGH.adjust(SweetnessAdjustment.NORMAL)).isEqualTo(FinalSweetness.HIGH);
        assertThat(DefaultSweetness.HIGH.adjust(SweetnessAdjustment.MORE)).isEqualTo(FinalSweetness.VERY_HIGH);
    }
}
