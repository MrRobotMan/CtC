use lettre::{
    transport::smtp::{
        authentication::{Credentials, Mechanism},
        PoolConfig,
    },
    Message, SmtpTransport, Transport,
};
use once_cell::sync::Lazy;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{self, Value};
use std::{
    env, fs,
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc,
    },
    thread,
    time::{self, Duration},
};

const BASE_URL: &str = "https://youtube.googleapis.com/youtube/v3";
const CTC_LATEST: &str = "videos.json";
static API_KEY: Lazy<String> = Lazy::new(|| env::var("YOUTUBE_KEY").unwrap());
static EMAIL_USER: Lazy<String> = Lazy::new(|| env::var("EMAIL_USER").unwrap());
static EMAIL_PASSWORD: Lazy<String> = Lazy::new(|| env::var("EMAIL_PASSWORD").unwrap());

pub fn main() {
    let stopped = Arc::new(AtomicBool::new(false));
    let stop = stopped.clone();
    ctrlc::set_handler(move || {
        stop.store(true, Ordering::SeqCst);
    })
    .expect("Error setting Ctrl+C handler");
    let (tx, rx) = mpsc::channel();
    let channel_data = get_last_seen();
    let mut video = Video::new(&channel_data.last_id);
    thread::spawn(move || {
        let modified = main_loop(channel_data, &mut video, &Arc::clone(&stopped));
        tx.send(modified).unwrap();
    });
    if let Ok(channel) = rx.recv() {
        write_last_seen(&channel);
    }
}

fn main_loop(mut channel: ChannelData, video: &mut Video, stop: &AtomicBool) -> ChannelData {
    loop {
        let (tx, rx) = mpsc::channel();
        if stop.load(Ordering::SeqCst) {
            let _ = tx.send(());
            return channel;
        }
        let channel_id = &channel.channel;
        let mut payload = format!("channels?part=contentDetails&id={channel_id}");
        let channel_data = get_data(&payload);
        let playlist_id = channel_data["contentDetails"]["relatedPlaylists"]["uploads"]
            .as_str()
            .unwrap();
        payload = format!(
            "playlistItems?part=snippet%2CcontentDetails&maxResults=1&playlistId={playlist_id}"
        );
        let vid = get_data(&payload);
        let latest_id = vid["contentDetails"]["videoId"].as_str().unwrap();
        let vid = Video::new(latest_id);
        let title = vid.title.to_lowercase();
        if video.youtube_id != vid.youtube_id
            && !title.contains("wordle")
            && !title.contains("crossword")
        {
            channel.last_id = vid.youtube_id.clone();
            *video = vid;
            send_email(video);
        }
        thread::spawn(
            move || {
                if rx.recv_timeout(Duration::from_secs(3600)).is_ok() {}
            },
        );
    }
}

fn send_email(video: &Video) {
    let email = Message::builder()
        .from(EMAIL_USER.as_str().parse().unwrap())
        .to(EMAIL_USER.as_str().parse().unwrap())
        .subject("Cracking the Cryptic")
        .body(video.message())
        .unwrap();
    let sender = SmtpTransport::starttls_relay("smtp.gmail.com")
        .unwrap()
        .credentials(Credentials::new(
            EMAIL_USER.as_str().to_owned(),
            EMAIL_PASSWORD.as_str().to_owned(),
        ))
        .authentication(vec![Mechanism::Plain])
        .pool_config(PoolConfig::new().max_size(20))
        .build();

    let _ = sender.send(&email);
}

/// Read the latest video data.
fn get_last_seen() -> ChannelData {
    serde_json::from_str::<ChannelData>(&fs::read_to_string(CTC_LATEST).unwrap()).unwrap()
}

/// Write the lastest information to the file.
fn write_last_seen(channel_data: &ChannelData) {
    let _ = fs::write(CTC_LATEST, serde_json::to_string(channel_data).unwrap());
}

/// Gather the useful information from the JSON object as a dictionary.
fn get_data(payload: &str) -> Value {
    let v: Value = serde_json::from_str(
        &reqwest::blocking::get(format!("{BASE_URL}/{payload}&key={}", API_KEY.as_str()))
            .unwrap()
            .text()
            .unwrap(),
    )
    .unwrap();
    v["items"][0].clone()
}

#[derive(Debug, Serialize, Deserialize)]
struct ChannelData {
    channel: String,
    last_id: String,
}

#[derive(Debug, Default, PartialEq, Eq, Clone)]
pub struct Video {
    title: String,
    sudoku_link: String,
    duration: time::Duration,
    youtube_id: String,
}

impl Video {
    fn new(video_id: &str) -> Self {
        let data = get_data(&format!(
            "videos?part=snippet%2CcontentDetails&id={video_id}"
        ));
        let title = match data["snippet"]["title"].as_str() {
            Some(t) => t.to_string(),
            None => String::new(),
        };
        let youtube_id = video_id.to_string();
        let run_time = data["contentDetails"]["duration"].to_string();
        let duration = get_duration(&run_time);
        let description = data["snippet"]["description"].to_string();
        let sudoku_link = match get_url(&description) {
            None => String::new(),
            Some(link) => link,
        };
        Self {
            title,
            sudoku_link,
            duration,
            youtube_id,
        }
    }

    fn time(&self) -> String {
        let seconds = self.duration.as_secs();
        let (hours, seconds) = divmod(seconds, 3600);
        let (minutes, seconds) = divmod(seconds, 60);
        format!("{hours}:{minutes}:{seconds}")
    }

    fn message(&self) -> String {
        format!(
            "The latest video {} (https://www.youtube.com/watch?v={}) for {} took {}.",
            self.title,
            self.youtube_id,
            self.sudoku_link,
            self.time()
        )
    }
}

fn divmod(t: u64, d: u64) -> (u64, u64) {
    (t / d, t % d)
}

fn get_url(text: &str) -> Option<String> {
    static URL_PATTERN: Lazy<Regex> = Lazy::new(|| {
        Regex::new(
            r"(https?):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])",
        )
        .unwrap()
    });
    // Pattern is
    // 1st group: https? = http or https
    // :\/\/ = :\\ (not captured)
    // 2nd group: ([\w_-]+(?:(?:\.[\w_-]+)+)) =
    //   [\w_-]+ => letters, numbers, _, - repeated
    //   (?:(?:\.[\w_-]+)+)) => non-capturing group of non-capturing group of ., letters, numbers, _, - repeated
    // 3rd group: ([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-]) => from / onward
    URL_PATTERN
        .captures(text)
        .map(|cap| cap.get(0).unwrap().as_str().into())
}

fn get_duration(duration: &str) -> Duration {
    static DURATION: Lazy<Regex> = Lazy::new(|| {
        // Pattern is PT<hours>H<minutes>M<seconds>S for ex: PT1H35M7S.
        Regex::new(r"PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?").unwrap()
    });
    let mut time = 0;
    let cap = DURATION.captures(duration).unwrap();
    if let Some(t) = cap.name("hours") {
        time += t.as_str().parse::<u64>().unwrap() * 3600;
    }
    if let Some(t) = cap.name("minutes") {
        time += t.as_str().parse::<u64>().unwrap() * 60;
    }
    if let Some(t) = cap.name("seconds") {
        time += t.as_str().parse::<u64>().unwrap();
    }
    Duration::from_secs(time)
}

pub fn get_yt_key() -> String {
    match env::var("YOUTUBE_KEY") {
        Ok(v) => v,
        _ => {
            let _ = dotenv::dotenv();
            get_yt_key()
        }
    }
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn test_video_simon() {
        let video_id = "029cB7l4qLg";
        let video = Video::new(video_id);
        let expected = Video {
            title: "The Sudoku Anniversary Sequel".into(),
            sudoku_link: "https://app.crackingthecryptic.com/sudoku/QgtR8b9Mr2".into(),
            duration: Duration::from_secs(3600 + 14 * 60 + 27),
            youtube_id: video_id.into(),
        };
        assert_eq!(expected, video);
    }

    #[test]
    fn test_video_mark() {
        let video_id = "RpMzNFA2W2c";
        let video = Video::new(video_id);
        let expected = Video {
            title: "Sudoku for a Happy Hippo".into(),
            sudoku_link: "https://tinyurl.com/CenterOfTheMoat".into(),
            duration: Duration::from_secs(37 * 60 + 45),
            youtube_id: video_id.into(),
        };
        assert_eq!(expected, video);
    }
}
