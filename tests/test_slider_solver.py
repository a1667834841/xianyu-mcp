import pytest

from src.api.slider_solver import SliderSolver


class FakeElement:
    def __init__(self, class_name=""):
        self.class_name = class_name

    async def get_attribute(self, name):
        if name == "class":
            return self.class_name
        return None


class FakeFrame:
    def __init__(self, elements=None):
        self.elements = elements or {}

    async def query_selector(self, selector):
        return self.elements.get(selector)


class FakePage:
    def __init__(self, url):
        self.url = url


class FakeMouse:
    def __init__(self):
        self.calls = []

    async def move(self, x, y, steps=None):
        self.calls.append(("move", x, y, steps))

    async def down(self):
        self.calls.append(("down",))

    async def up(self):
        self.calls.append(("up",))


class FakeDragPage:
    def __init__(self):
        self.mouse = FakeMouse()


class FakeDraggableElement:
    def __init__(self):
        self.hover_calls = 0

    async def bounding_box(self):
        return {"x": 10, "y": 20, "width": 30, "height": 40}

    async def hover(self):
        self.hover_calls += 1


@pytest.mark.asyncio
async def test_check_result_does_not_treat_missing_container_on_captcha_page_as_success():
    solver = SliderSolver()
    frame = FakeFrame(elements={})
    page = FakePage("https://h5api.m.goofish.com/_____tmd_____/punish?action=captcha")

    result = await solver._check_result(frame, page)

    assert result is False


@pytest.mark.asyncio
async def test_check_result_accepts_success_marker():
    solver = SliderSolver()
    frame = FakeFrame(elements={"#baxia-dialog-content": FakeElement(class_name="nc success")})
    page = FakePage("https://h5api.m.goofish.com/_____tmd_____/punish?action=captcha")

    result = await solver._check_result(frame, page)

    assert result is True


@pytest.mark.asyncio
async def test_check_result_accepts_navigation_away_from_captcha():
    solver = SliderSolver()
    frame = FakeFrame(elements={"#baxia-dialog-content": FakeElement(class_name="")})
    page = FakePage("https://www.goofish.com/")

    result = await solver._check_result(frame, page)

    assert result is True


@pytest.mark.asyncio
async def test_find_slider_frame_reuses_cached_frame_when_available():
    solver = SliderSolver()
    cached_frame = FakeFrame(elements={"#baxia-dialog-content": FakeElement()})
    solver._detected_slider_frame = cached_frame
    page = FakePage("https://example.com")

    frame = await solver._find_slider_frame(page)

    assert frame is cached_frame


@pytest.mark.asyncio
async def test_simulate_drag_uses_mouse_drag_sequence():
    solver = SliderSolver()
    page = FakeDragPage()
    element = FakeDraggableElement()
    trajectory = [(5, 1, 0), (10, -1, 0)]

    await solver._simulate_drag(page, element, trajectory)

    assert page.mouse.calls[0] == ("move", 25.0, 40.0, None)
    assert page.mouse.calls[1] == ("down",)
    assert page.mouse.calls[-1] == ("up",)
    assert any(call[:1] == ("move",) and call[1] == 30.0 for call in page.mouse.calls)
