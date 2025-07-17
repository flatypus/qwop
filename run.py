from multiprocessing import Process, Value
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from tesserocr import PyTessBaseAPI
import asyncio
import ctypes
import multiprocessing
import os
import random
import re
import subprocess
import time

PROGRESS_THRESHOLD = 0.8

if not os.path.exists("timelapse"):
    os.makedirs("timelapse")


def screenshot_monitor(score_val, stop_flag):
    def detect_text(img):
        with PyTessBaseAPI(path="/opt/homebrew/share/tessdata") as tess:
            tess.SetImage(img)
            text = tess.GetUTF8Text()
        return text

    time.sleep(3)
    while not stop_flag.value:
        # need to move 0.8 m / 5 seconds at least
        time.sleep(5)
        try:
            screenshot = Image.open("screenshot.png")
            text = detect_text(screenshot)
            score = None
            try:
                matches = re.findall(r"-?\d+(?:\.\d+)?(?= met)", text)
                # pick min so it doesn't accidentally use the on screen one that keeps running
                if matches:
                    score = min(float(m) for m in matches)
            except:
                pass

            bad_score = False
            if not score is None:
                if score_val.value > score:
                    print(
                        f"Score decreased from {score_val.value} to {score}, ending...")
                    score_val.value = score
                    bad_score = True
                elif abs(score_val.value - score) < PROGRESS_THRESHOLD:
                    print("Not enough progress was made, ending...")
                    score_val.value = round(score, 2)
                    bad_score = True
                else:
                    score_val.value = round(score, 2)

            game_over = "participant" in text.lower() or "national" in text.lower()

            if game_over or bad_score:
                stop_flag.value = 1
                print(f"Game over: {game_over}")
                break

        except Exception as e:
            pass


class Game:
    def __init__(self):
        self.prepare_driver()
        self.score = 0
        self.over = False
        self.screenshot_process = None
        self.score_val = None
        self.stop_flag = None
        self.KEY_PRESS_TIME = 0.05

    def prepare_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--mute-audio")
        self.driver = webdriver.Chrome(options=options)
        self.actions = ActionChains(self.driver)
        self.driver.get("https://www.foddy.net/Athletics.html")
        time.sleep(3)
        self.click_center()

    def auto_kill(self):
        self.key_down("o")
        self.key_down("p")
        time.sleep(2)
        self.key_up("o")
        self.key_up("p")

    def reset_game(self):
        self.key_down("r")
        self.key_up("r")
        time.sleep(0.5)
        self.score = 0
        self.over = False

    def start_monitoring(self):
        self.score_val = Value(ctypes.c_float, 0)
        self.stop_flag = Value(ctypes.c_int, 0)

        self.screenshot_process = Process(
            target=screenshot_monitor,
            args=(self.score_val, self.stop_flag)
        )
        self.screenshot_process.start()

    def stop_monitoring(self):
        if self.screenshot_process and self.screenshot_process.is_alive():
            self.stop_flag.value = 1
            self.screenshot_process.join(timeout=5)
            if self.screenshot_process.is_alive():
                self.screenshot_process.terminate()
                self.screenshot_process.join()

    def update_from_monitor(self):
        self.score = round(float(self.score_val.value), 2)
        self.over = self.stop_flag.value == 1

    async def execute_pattern(self, pattern):
        self.screenshot()
        for index, key in enumerate(pattern):
            self.update_from_monitor()

            if self.over:
                break

            self.key_down(key)
            await asyncio.sleep(self.KEY_PRESS_TIME)
            self.key_up(key)

            if index % 60 == 0:
                self.screenshot()

    def get_current_score(self):
        self.update_from_monitor()
        return self.score

    def is_game_over(self):
        self.update_from_monitor()
        return self.over

    def screenshot(self):
        self.driver.save_screenshot("screenshot.png")
        path = f"./timelapse/screenshot_{time.time()}.png"
        subprocess.run(["cp", "./screenshot.png", path])

    def key_down(self, key):
        self.actions.key_down(key).perform()

    def key_up(self, key):
        self.actions.key_up(key).perform()

    def click_center(self):
        self.actions.move_by_offset(100, 100).click().perform()


class Evolution:
    def __init__(self, game_instance):
        START_PATTERNS = 12
        self.MIN_LENGTH = 40
        self.MAX_LENGTH = 160

        self.game = game_instance
        self.patterns = self.get_patterns(START_PATTERNS)

    def get_pattern(self):
        length = random.randint(self.MIN_LENGTH, self.MAX_LENGTH)
        pattern = []
        for i in range(length):
            pattern.append(random.choice(["q", "p", "w", "o"]))
        return pattern

    def get_patterns(self, n):
        return [self.get_pattern() for _ in range(n)]

    def evolve_n(self, pattern, n):
        original_pattern = pattern.copy()
        new_patterns = []
        for i in range(n):
            new_pattern = original_pattern.copy()
            mutations = random.randint(1, len(new_pattern) // 2)
            for _ in range(mutations):
                mut_point = random.randint(0, len(new_pattern) - 1)
                new_pattern[mut_point] = random.choice(["q", "p", "w", "o"])
            new_patterns.append(new_pattern)
        return new_patterns

    async def test_pattern(self, pattern):
        score = float('-inf')
        self.game.start_monitoring()
        self.game.reset_game()
        start = time.time()

        try:
            for run in range(self.REPEAT_PATTERN_FOR):
                print(f"Run {run+1}/{self.REPEAT_PATTERN_FOR}")
                await self.game.execute_pattern(pattern)
                score = self.game.get_current_score()
                if self.game.is_game_over():
                    break
            self.game.auto_kill()

        finally:
            self.game.stop_monitoring()

        end = time.time()
        speed = abs(score) / (end - start)
        final_score = score + speed
        return score, final_score

    async def test_patterns(self, patterns):
        results = []

        for i, pattern in enumerate(patterns):
            print(f"\nTesting pattern {i+1}/{len(patterns)}")
            score, final_score = await self.test_pattern(pattern)
            results.append([pattern, score, final_score])
            print(
                f"Pattern {i+1} distance: {score}, final score: {final_score}")

        return results

    def log_best(self, results):
        with open("best.txt", "a") as f:
            for pattern, score, final_score in results:
                text = f"Score of {score}; final score: {final_score}; pattern: {pattern}"
                print(text)
                f.write(text + "\n")

    async def evolve_generation(self, KEEP_BEST_N=3, EVOLVE_N=3, ADD_NEW_N=3, REPEAT_PATTERN_FOR=10):
        self.KEEP_BEST_N = KEEP_BEST_N
        self.EVOLVE_N = EVOLVE_N
        self.ADD_NEW_N = ADD_NEW_N
        self.REPEAT_PATTERN_FOR = REPEAT_PATTERN_FOR

        results = await self.test_patterns(self.patterns)

        results = sorted(results, key=lambda x: x[2], reverse=True)

        best_n = results[:self.KEEP_BEST_N]
        self.log_best(best_n)

        new_patterns = []

        print("Evolving...")
        for index, data in enumerate(best_n):
            pattern = data[0]
            new_patterns.append(pattern)
            new_patterns.extend(self.evolve_n(pattern, self.EVOLVE_N - index))

        new_patterns.extend(self.get_patterns(self.ADD_NEW_N))

        self.patterns = new_patterns
        return best_n


async def main():
    multiprocessing.set_start_method('spawn', force=True)

    game = Game()
    evolution = Evolution(game)

    generation = 0
    try:
        while True:
            generation += 1
            print(f"\n=== Generation {generation} ===")

            best_results = await evolution.evolve_generation(
                KEEP_BEST_N=3,
                EVOLVE_N=5,
                ADD_NEW_N=3,
                REPEAT_PATTERN_FOR=300
            )

            print(f"Best score this generation: {best_results[0][2]}")

    except KeyboardInterrupt:
        print("\nEvolution stopped by user")
    finally:
        game.stop_monitoring()
        if game.driver:
            game.driver.quit()


if __name__ == "__main__":
    asyncio.run(main())
