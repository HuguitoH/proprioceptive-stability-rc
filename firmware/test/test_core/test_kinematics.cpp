#include <unity.h>

#include "kinematics.h"

void setUp() {}
void tearDown() {}

// Two magnets: 2 pulses are one revolution.
void test_rpm_one_revolution_per_second_is_60_rpm() {
  TEST_ASSERT_FLOAT_WITHIN(1e-4f, 60.0f, core::driveshaftRpm(2, 1.0f, 2));
}

void test_rpm_scales_with_the_interval() {
  TEST_ASSERT_FLOAT_WITHIN(1e-4f, 120.0f, core::driveshaftRpm(2, 0.5f, 2));
}

void test_rpm_is_zero_without_pulses() {
  TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, core::driveshaftRpm(0, 0.5f, 2));
}

void test_rpm_is_zero_for_a_non_positive_interval() {
  TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, core::driveshaftRpm(10, 0.0f, 2));
  TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, core::driveshaftRpm(10, -1.0f, 2));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_rpm_one_revolution_per_second_is_60_rpm);
  RUN_TEST(test_rpm_scales_with_the_interval);
  RUN_TEST(test_rpm_is_zero_without_pulses);
  RUN_TEST(test_rpm_is_zero_for_a_non_positive_interval);
  return UNITY_END();
}
