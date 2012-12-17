function Chat(id) {
    this.el = $('#'+id);
}

Chat.prototype.message = function (obj) {
    var ts = new Date(obj.ts)
    var msg = $('<div>')
        .append($('<span class="ts">').text('['+ts.getHours()+':'+ts.getMinutes()+'] '));
    switch (obj.cmd) {
        case 'say':
        msg.append($('<span class="nick">').text(obj.user+": "),
                   $('<span class="say">').text(obj.message));
        break;

        case 'join':
        case 'leave':
        msg.append($('<span>').addClass(obj.cmd)
                   .text(obj.user+" "+(obj.cmd == 'join' ? "joins." : "leaves.")));
        break;
    }
    msg.appendTo(this.el);
};


function login(username) {
    $.ajax({ url: '/ajax/login',
             data: { 'name': username },
             type: 'POST'
           });
}

function message(msg) {
    $.ajax({ url: '/ajax/post',
             data: { 'message': msg },
             type: 'POST'
           });
}   

(function poll(){
    $.ajax({ url: "/ajax/poll", success: function(data){
        for (var i in data) {
            chat.message(data[i]);
        }
    }, dataType: "json", complete: poll, timeout: 30000 });
})();


var chat;

$(document).ready(function () {
    chat = new Chat("chat");

    $('#loginbtn').click(function () {
        if ($('#username').val()) {
            login($('#username').val());
            $('#login').hide();

            $("#inputline").attr('disabled', null);
            $("#sendbtn").attr('disabled', null);

            $("#chat").show();
            $("#input").show();

            $("#sendbtn").click(function () {
                message($("#inputline").val());
                $("#inputline").val('').focus();
            });

            $('#inputline').keyup(function (evt) {
                if (evt.keyCode == 13) {
                    $('#sendbtn').click();
                }
            });
        }
    });
});
