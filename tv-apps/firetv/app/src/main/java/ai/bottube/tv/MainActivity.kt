package ai.bottube.tv

import android.app.Activity
import android.os.Bundle
import android.widget.TextView

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val tv = TextView(this)
        tv.text = "BoTTube TV (Fire TV)\nTrending + Fullscreen playback scaffold"
        tv.textSize = 24f
        setContentView(tv)
    }
}
