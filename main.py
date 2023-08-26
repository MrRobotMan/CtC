import json
import re
import time
from typing import Any

import requests

with open(".env", encoding="utf8") as dotenv:
    API_KEY = dotenv.readline().strip().split("=")[1]
BASE_URL = "https://youtube.googleapis.com/youtube/v3"

URL_PATTERN = re.compile(
    R"(https?):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])"
)
# Pattern is
# 1st group: https? = http or https
# :\/\/ = :\\ (not captured)
# 2nd group: ([\w_-]+(?:(?:\.[\w_-]+)+)) =
#   [\w_-]+ => letters, numbers, _, - repeated
#   (?:(?:\.[\w_-]+)+)) => non-capturing group of non-capturing group of ., letters, numbers, _, - repeated
# 3rd group: ([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-]) => from / onward


def main():
    channel_id = "UCC-UOdK8-mIjxBQm_ot1T-Q"
    channel = get_data(f"channels?part=contentDetails&id={channel_id}")

    playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    video = get_data(
        f"playlistItems?part=snippet%2CcontentDetails&maxResults=1&playlistId={playlist_id}"
    )

    lastest_id = video["contentDetails"]["videoId"]

    data = get_data(f"videos?part=snippet%2CcontentDetails&id={lastest_id}")
    run_time = time.strptime(data["contentDetails"]["duration"], "PT%MM%SS")
    description = data["snippet"]["description"]
    title = data["snippet"]["title"]

    url = [
        link.group(0)
        for link in URL_PATTERN.finditer(description)
        if "tinyurl.com" in link.group(0).lower()
        or "sudokupad.app" in link.group(0).lower()
    ][0]
    print(
        f"The latest video {title} ({url}) took {time.strftime('%H:%M:%S', run_time)}."
    )


def get_data(payload: str) -> dict[str, Any]:
    return json.loads(
        requests.get(f"{BASE_URL}/{payload}&key={API_KEY}", timeout=5).text
    )["items"][0]


if __name__ == "__main__":
    main()
